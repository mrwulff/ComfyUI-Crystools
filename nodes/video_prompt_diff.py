"""Compare meaningful prompt/settings differences between two ComfyUI video outputs."""
import difflib
import json
import os
import re
import subprocess
from pathlib import Path

import folder_paths
from ..core import CATEGORY


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}


def _resolve_path(value):
    """Resolve an absolute path or a path relative to ComfyUI input/output."""
    if not value or not str(value).strip():
        raise ValueError("Choose both videos with the Browse buttons, or enter a full path.")
    path = Path(os.path.expandvars(os.path.expanduser(str(value).strip().strip('"'))))
    if path.is_file():
        if path.suffix.lower() not in VIDEO_EXTENSIONS:
            raise ValueError("Unsupported video extension: " + path.suffix)
        return path.resolve()
    for root_getter in (folder_paths.get_input_directory, folder_paths.get_output_directory):
        root = root_getter()
        candidate = (Path(root) / path).resolve()
        if candidate.is_file():
            if candidate.suffix.lower() not in VIDEO_EXTENSIONS:
                raise ValueError("Unsupported video extension: " + candidate.suffix)
            return candidate
    raise FileNotFoundError("Video not found: " + str(value))


def _parse_json_tag(tags, name):
    value = tags.get(name)
    if not value:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


def _read_video_metadata(path):
    """Read embedded ComfyUI prompt/workflow metadata with ffprobe; no video decoding."""
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-show_format", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=45, check=False
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "ffprobe was not found. Install FFmpeg and add its bin folder to PATH, then restart ComfyUI."
        ) from exc
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or "ffprobe could not read this video.").strip())
    try:
        tags = json.loads(proc.stdout).get("format", {}).get("tags", {})
    except json.JSONDecodeError as exc:
        raise RuntimeError("ffprobe returned invalid metadata JSON.") from exc

    # MP4 tag names are not guaranteed to have a consistent case.
    tags = {str(k).lower(): v for k, v in tags.items()}
    prompt = _parse_json_tag(tags, "prompt")
    workflow = _parse_json_tag(tags, "workflow")
    if not isinstance(prompt, dict) and not isinstance(workflow, dict):
        raise ValueError(
            "No embedded ComfyUI prompt/workflow metadata found in " + path.name +
            ". This video may have been re-encoded or exported without metadata."
        )
    return {
        "prompt": prompt if isinstance(prompt, dict) else {},
        "workflow": workflow if isinstance(workflow, dict) else {},
    }


def _clean_value(value):
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip()
    return value


def _extract_prompt_values(prompt, workflow, include_settings, ignore_seed):
    """Extract scalar inputs from the execution graph, using workflow titles to identify text nodes."""
    result = {}
    if not isinstance(prompt, dict):
        return result

    workflow_nodes = {}
    if isinstance(workflow, dict):
        for node in workflow.get("nodes", []) if isinstance(workflow.get("nodes"), list) else []:
            if isinstance(node, dict):
                workflow_nodes[str(node.get("id"))] = node

    text_input = re.compile(r"(text|prompt|negative|positive|caption|description|lyrics|system_prompt)", re.I)
    text_node = re.compile(r"(prompt|text|stringmultiline|textencode|caption|builder|qwen)", re.I)
    setting_input = re.compile(
        r"(model|lora|seed|steps|cfg|guidance|sampler|scheduler|width|height|frames|length|fps|"
        r"strength|temperature|shift|noise|resolution|duration|aspect|clip_name|vae_name|unet_name)", re.I
    )
    ignored_keys = {"filename_prefix", "video-preview", "preview_method", "preview_rate"}

    for node_id, node in prompt.items():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            continue
        class_type = str(node.get("class_type", "node"))
        wf_node = workflow_nodes.get(str(node_id), {})
        title = str(wf_node.get("title") or node.get("_meta", {}).get("title") or "")
        node_label = title or class_type
        text_context = bool(text_node.search(class_type + " " + title))

        for input_name, value in inputs.items():
            key_name = str(input_name)
            if key_name in ignored_keys or isinstance(value, (dict, list)):
                # Lists/dicts in the execution prompt generally encode links.
                continue
            if ignore_seed and re.search(r"seed", key_name, re.I):
                continue
            is_text = bool(text_input.search(key_name))
            # H3 workflows often place enormous prompt strings on generic "value"
            # or "template" inputs of PrimitiveStringMultiline / PromptBuilder nodes.
            if not is_text and text_context and key_name.lower() in {
                "value", "template", "all_chunks", "appearance", "outfit",
                "location", "action", "character", "system_prompt"
            }:
                is_text = True
            is_setting = include_settings and bool(setting_input.search(key_name))
            if not is_text and not is_setting:
                continue
            if not isinstance(value, (str, int, float, bool)):
                continue
            value = _clean_value(value)
            if value == "":
                continue
            group = "Prompt" if is_text else "Setting"
            key = group + " / " + node_label + " [" + class_type + "] / " + key_name
            if key in result:
                key += " (node " + str(node_id) + ")"
            result[key] = value

    # In ComfyUI's executed prompt, a text node may only contain a link such as
    # ["5861", 0], while the actual widget text lives in workflow.widgets_values_named.
    # Read text widgets from relevant nodes too; this catches H3 "Positive Prompt"
    # nodes whose value is supplied by a linked output.
    if isinstance(workflow, dict):
        for wf_node in workflow.get("nodes", []) if isinstance(workflow.get("nodes"), list) else []:
            if not isinstance(wf_node, dict):
                continue
            named = wf_node.get("widgets_values_named")
            if not isinstance(named, dict):
                continue
            wf_title = str(wf_node.get("title") or "")
            wf_type = str(wf_node.get("type") or "")
            if not text_node.search(wf_title + " " + wf_type):
                continue
            for input_name, value in named.items():
                input_name = str(input_name)
                if input_name.lower() not in {
                    "value", "text", "prompt", "positive", "negative", "template",
                    "all_chunks", "appearance", "outfit", "location", "action",
                    "character", "system_prompt"
                }:
                    continue
                if isinstance(value, (dict, list)) or not isinstance(value, (str, int, float, bool)):
                    continue
                value = _clean_value(value)
                if value == "":
                    continue
                label = wf_title or wf_type
                key = "Prompt / " + label + " [" + wf_type + "] / " + input_name
                if key in result and result[key] != value:
                    key += " (workflow widget)"
                result[key] = value

    return result


def _workflow_settings(workflow, ignore_seed):
    """Collect useful named model/generation settings from workflow widgets."""
    result = {}
    if not isinstance(workflow, dict):
        return result
    setting_key = re.compile(
        r"(model|lora|seed|steps|cfg|guidance|sampler|scheduler|width|height|frames|length|fps|"
        r"strength|shift|noise|resolution|duration|aspect|clip_name|vae_name|unet_name|weight_dtype)", re.I
    )
    for node in workflow.get("nodes", []) if isinstance(workflow.get("nodes"), list) else []:
        if not isinstance(node, dict):
            continue
        named = node.get("widgets_values_named")
        if not isinstance(named, dict):
            continue
        title = str(node.get("title") or node.get("type") or "node")
        for name, value in named.items():
            name = str(name)
            if not setting_key.search(name):
                continue
            if ignore_seed and re.search(r"seed", name, re.I):
                continue
            if isinstance(value, (dict, list)):
                continue
            value = _clean_value(value)
            key = "Setting / " + title + " / " + name
            if key in result:
                key += " (node " + str(node.get("id", "")) + ")"
            result[key] = value
    return result


def _shorten(value, limit=420):
    value = str(value)
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + " … [truncated]"


def _word_diff(old, new, max_changes=16):
    """Emit only changed word fragments; never repeat a whole prompt by default."""
    old_words = str(old).split()
    new_words = str(new).split()
    matcher = difflib.SequenceMatcher(None, old_words, new_words, autojunk=False)
    fragments = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        removed = " ".join(old_words[i1:i2])
        added = " ".join(new_words[j1:j2])
        if removed:
            fragments.append("- " + _shorten(removed))
        if added:
            fragments.append("+ " + _shorten(added))
        if len(fragments) >= max_changes:
            fragments.append("… further changed fragments omitted")
            break
    return "\n    ".join(fragments) if fragments else "(text differs only in whitespace)"


def _format_diff(path_a, path_b, metadata_a, metadata_b, compare, ignore_seed):
    prompt_only = compare == "Prompt text only"
    old_values = _extract_prompt_values(
        metadata_a["prompt"], metadata_a["workflow"], not prompt_only, ignore_seed
    )
    new_values = _extract_prompt_values(
        metadata_b["prompt"], metadata_b["workflow"], not prompt_only, ignore_seed
    )
    if compare == "Prompt + settings":
        old_values.update(_workflow_settings(metadata_a["workflow"], ignore_seed))
        new_values.update(_workflow_settings(metadata_b["workflow"], ignore_seed))

    changes = []
    for key in sorted(set(old_values) | set(new_values), key=str.casefold):
        if key not in new_values:
            value = old_values[key]
            # When removing a prompt field, truncate it rather than flood the output.
            changes.append("REMOVED  " + key + "\n    - " + _shorten(value))
        elif key not in old_values:
            value = new_values[key]
            changes.append("ADDED    " + key + "\n    + " + _shorten(value))
        elif old_values[key] != new_values[key]:
            old, new = old_values[key], new_values[key]
            if isinstance(old, str) and isinstance(new, str) and (
                key.startswith("Prompt / ") or max(len(old), len(new)) > 160
            ):
                body = _word_diff(old, new)
                changes.append("CHANGED  " + key + "\n    " + body)
            else:
                changes.append(
                    "CHANGED  " + key + "\n    - " + _shorten(old, 220) +
                    "\n    + " + _shorten(new, 220)
                )

    header = (
        "Video Prompt Diff\n"
        "A: " + path_a.name + "\n"
        "B: " + path_b.name + "\n"
        "Mode: " + compare + "\n"
    )
    if not changes:
        return header + "\nNo differences found in the selected fields."
    return header + "\n" + "\n\n".join(changes)


class CVideoPromptDiff:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video_a": ("STRING", {"default": "", "multiline": False}),
                "video_b": ("STRING", {"default": "", "multiline": False}),
                "compare": (["Prompt text only", "Prompt + settings"],),
                "ignore_seed": ("BOOLEAN", {"default": True}),
            }
        }

    CATEGORY = CATEGORY.MAIN.value + CATEGORY.METADATA.value
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("diff",)
    FUNCTION = "execute"
    OUTPUT_NODE = True

    def execute(self, video_a, video_b, compare="Prompt text only", ignore_seed=True):
        try:
            path_a = _resolve_path(video_a)
            path_b = _resolve_path(video_b)
            metadata_a = _read_video_metadata(path_a)
            metadata_b = _read_video_metadata(path_b)
            diff = _format_diff(path_a, path_b, metadata_a, metadata_b, compare, ignore_seed)
        except Exception as exc:
            diff = "Video Prompt Diff error\n" + str(exc)
        return {"ui": {"text": [diff]}, "result": (diff,)}
