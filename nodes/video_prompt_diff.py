"""Compare meaningful prompt/settings differences between two ComfyUI MP4 outputs."""
import json
import os
import re
import subprocess
from pathlib import Path

import folder_paths
from ..core import CATEGORY


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}


def _video_choices():
    """Return absolute paths so videos can be selected from ComfyUI input/output folders."""
    found = []
    seen = set()
    for root in (folder_paths.get_output_directory(), folder_paths.get_input_directory()):
        if not root or not os.path.isdir(root):
            continue
        for current, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for name in files:
                if Path(name).suffix.lower() not in VIDEO_EXTENSIONS:
                    continue
                path = os.path.abspath(os.path.join(current, name))
                if path not in seen:
                    found.append(path)
                    seen.add(path)
    return sorted(found, key=str.casefold) or [""]


def _resolve_path(value):
    if not value:
        raise ValueError("No video selected. Put both videos in ComfyUI/output or ComfyUI/input and refresh/restart ComfyUI.")
    path = Path(os.path.expandvars(os.path.expanduser(str(value))))
    if path.is_file():
        return path.resolve()
    for root_getter in (folder_paths.get_output_directory, folder_paths.get_input_directory):
        root = root_getter()
        candidate = Path(root) / path
        if candidate.is_file():
            return candidate.resolve()
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


def _read_mp4_metadata(path):
    """Read MP4 metadata with ffprobe without decoding the video."""
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-show_format", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=30, check=False
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "ffprobe.exe was not found. Install FFmpeg and add its bin folder to PATH, then restart ComfyUI."
        ) from exc
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or "ffprobe could not read the video metadata.").strip())
    try:
        tags = json.loads(proc.stdout).get("format", {}).get("tags", {})
    except json.JSONDecodeError as exc:
        raise RuntimeError("ffprobe returned invalid metadata JSON.") from exc
    prompt = _parse_json_tag(tags, "prompt")
    workflow = _parse_json_tag(tags, "workflow")
    if not isinstance(prompt, dict) and not isinstance(workflow, dict):
        raise ValueError(
            "No embedded ComfyUI prompt/workflow metadata found in " + path.name +
            ". This node needs an MP4 with prompt or workflow metadata."
        )
    return {"prompt": prompt if isinstance(prompt, dict) else {},
            "workflow": workflow if isinstance(workflow, dict) else {}}


def _clean_value(value):
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip()
    return value


def _extract_values(prompt, include_settings, ignore_seed):
    """Flatten ComfyUI's executed prompt graph into human-meaningful scalar values."""
    result = {}
    if not isinstance(prompt, dict):
        return result

    text_key = re.compile(r"(text|prompt|negative|positive|caption|description|lyrics|system_prompt)", re.I)
    setting_key = re.compile(
        r"(model|lora|seed|steps|cfg|guidance|sampler|scheduler|width|height|frames|length|fps|"
        r"strength|temperature|shift|noise|resolution|duration|aspect|clip_name|vae_name|unet_name)", re.I
    )
    ignored_keys = {"filename_prefix", "video-preview", "preview_method", "preview_rate"}

    # Use node title/class + input name instead of numeric node ID where possible.
    for node_id, node in prompt.items():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            continue
        meta = node.get("_meta", {})
        title = meta.get("title") if isinstance(meta, dict) else None
        class_type = str(node.get("class_type", "node"))
        label = str(title or class_type)

        for input_name, value in inputs.items():
            key_name = str(input_name)
            if key_name in ignored_keys or isinstance(value, (dict, list)):
                # Lists in execution prompts commonly represent graph links.
                continue
            is_text = bool(text_key.search(key_name))
            if not is_text and not (include_settings and setting_key.search(key_name)):
                continue
            if ignore_seed and re.search(r"seed", key_name, re.I):
                continue
            if not isinstance(value, (str, int, float, bool)):
                continue
            value = _clean_value(value)
            if value == "":
                continue
            key = label + " [" + class_type + "] / " + key_name
            # Duplicate node titles are rare; append the ID only for collisions.
            if key in result:
                key += " (node " + str(node_id) + ")"
            result[key] = value
    return result


def _workflow_settings(workflow, ignore_seed):
    """Read named widget values for settings stored in workflow but absent from executed prompt."""
    result = {}
    if not isinstance(workflow, dict):
        return result
    setting_key = re.compile(
        r"(model|lora|seed|steps|cfg|guidance|sampler|scheduler|width|height|frames|length|fps|"
        r"strength|shift|noise|resolution|duration|aspect|text|prompt|clip|vae|unet)", re.I
    )
    for node in workflow.get("nodes", []) if isinstance(workflow.get("nodes"), list) else []:
        if not isinstance(node, dict):
            continue
        named = node.get("widgets_values_named")
        if not isinstance(named, dict):
            continue
        title = str(node.get("title") or node.get("type") or "node")
        for name, value in named.items():
            if not setting_key.search(str(name)):
                continue
            if ignore_seed and re.search(r"seed", str(name), re.I):
                continue
            if isinstance(value, (dict, list)):
                continue
            value = _clean_value(value)
            key = title + " / " + str(name)
            if key in result:
                key += " (node " + str(node.get("id", "")) + ")"
            result[key] = value
    return result


def _make_diff(path_a, path_b, meta_a, meta_b, compare, ignore_seed):
    text_only = compare == "Prompt text only"
    old_values = _extract_values(meta_a["prompt"], not text_only, ignore_seed)
    new_values = _extract_values(meta_b["prompt"], not text_only, ignore_seed)
    if compare == "Prompt + settings":
        # Workflow widgets contain values not represented in the executed prompt
        # (such as bypassed nodes), so include them in the settings comparison too.
        old_values.update({"Workflow / " + k: v for k, v in _workflow_settings(meta_a["workflow"], ignore_seed).items()})
        new_values.update({"Workflow / " + k: v for k, v in _workflow_settings(meta_b["workflow"], ignore_seed).items()})

    changes = []
    for key in sorted(set(old_values) | set(new_values), key=str.casefold):
        if key not in new_values:
            changes.append("REMOVED  " + key + "\n  - " + str(old_values[key]))
        elif key not in old_values:
            changes.append("ADDED    " + key + "\n  + " + str(new_values[key]))
        elif old_values[key] != new_values[key]:
            changes.append("CHANGED  " + key + "\n  - " + str(old_values[key]) + "\n  + " + str(new_values[key]))

    header = "Video Prompt Diff\nA: " + path_a.name + "\nB: " + path_b.name + "\nMode: " + compare + "\n"
    if not changes:
        return header + "\nNo differences found in the selected fields."
    return header + "\n" + "\n\n".join(changes)


class CVideoPromptDiff:
    @classmethod
    def INPUT_TYPES(cls):
        choices = _video_choices()
        return {
            "required": {
                "video_a": (choices,),
                "video_b": (choices,),
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
            metadata_a = _read_mp4_metadata(path_a)
            metadata_b = _read_mp4_metadata(path_b)
            diff = _make_diff(path_a, path_b, metadata_a, metadata_b, compare, ignore_seed)
        except Exception as exc:
            diff = "Video Prompt Diff error\n" + str(exc)
        return {"ui": {"text": [diff]}, "result": (diff,)}
