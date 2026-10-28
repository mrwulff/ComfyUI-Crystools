import { app } from './comfy/index.js';
import { displayContext } from './common.js';
const crystoolsExtensionsSerialized = {
    'Read JSON file [Crystools]': 'Crystools.Utils.ReadJsonFile',
    'JSON extractor [Crystools]': 'Crystools.Utils.JsonExtractor',
};
const crystoolsExtensions = {
    'Get resolution [Crystools]': 'Crystools.Image.GetResolution',
    'Preview from image [Crystools]': 'Crystools.Image.PreviewFromImage',
    'Preview from metadata [Crystools]': 'Crystools.Image.PreviewFromMetadata',
    'Metadata comparator [Crystools]': 'Crystools.Metadata.MetadataComparator',
    'Stats system [Crystools]': 'Crystools.Utils.StatsSystem',
    'Show any to JSON [Crystools]': 'Crystools.Debugger.ConsoleAnyToJson',
};
Object.keys(crystoolsExtensionsSerialized).forEach(prop => {
    crystoolsExtensions[prop] = crystoolsExtensionsSerialized[prop];
});
Object.keys(crystoolsExtensions).forEach(key => {
    app.registerExtension({
        name: crystoolsExtensions[key],
        beforeRegisterNodeDef(nodeType, nodeData, appFromArg) {
            if (nodeData.name === key) {
                if (nodeData.name in crystoolsExtensionsSerialized) {
                    displayContext(nodeType, appFromArg, 0, true);
                }
                else {
                    displayContext(nodeType, appFromArg, 0);
                }
            }
        },
    });
});


// Render a compact, color-coded diff inside the node instead of plain monochrome text.
function renderVideoDiff(panel, text) {
    panel.replaceChildren();
    if (!text || !text.trim()) {
        panel.textContent = "No diff returned. Check the ComfyUI terminal for errors.";
        return;
    }

    const lines = text.split(/\r?\n/);
    const header = document.createElement("div");
    header.style.cssText = "display:flex;flex-direction:column;gap:2px;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid #454545;";
    const title = document.createElement("div");
    title.textContent = lines[0] || "Video Prompt Diff";
    title.style.cssText = "font:bold 13px/1.4 sans-serif;color:var(--input-text,#eee);";
    header.appendChild(title);

    for (const line of lines.slice(1, 4)) {
        if (!line.trim()) continue;
        const metadata = document.createElement("div");
        metadata.textContent = line;
        metadata.style.cssText = "font:11px/1.4 sans-serif;color:#a7adb7;";
        header.appendChild(metadata);
    }
    panel.appendChild(header);

    const rest = lines.slice(4).join("\n").trim();
    if (!rest) {
        const empty = document.createElement("div");
        empty.textContent = "No differences found.";
        empty.style.cssText = "padding:8px;color:#a7adb7;font:12px sans-serif;";
        panel.appendChild(empty);
        return;
    }
    if (rest.startsWith("No differences found")) {
        const empty = document.createElement("div");
        empty.textContent = rest;
        empty.style.cssText = "padding:10px;color:#82d9a0;font:12px sans-serif;";
        panel.appendChild(empty);
        return;
    }
    if (rest.startsWith("Video Prompt Diff error")) {
        const error = document.createElement("div");
        error.textContent = rest;
        error.style.cssText = "padding:10px;color:#ff8f8f;white-space:pre-wrap;";
        panel.appendChild(error);
        return;
    }

    const blocks = rest.split(/\n\s*\n/).filter(block => block.trim());
    let added = 0, removed = 0, changed = 0;
    for (const block of blocks) {
        const blockLines = block.split(/\r?\n/);
        const first = blockLines.shift() || "";
        const match = first.match(/^\s*(CHANGED|ADDED|REMOVED)\s+(.*)$/i);
        const status = (match?.[1] || "INFO").toUpperCase();
        const label = match?.[2] || first;
        if (status === "ADDED") added++;
        else if (status === "REMOVED") removed++;
        else if (status === "CHANGED") changed++;

        let accent = "#8d969f", bg = "rgba(130,140,150,.08)", badgeBg = "rgba(130,140,150,.16)", badgeText = "#d1d5da";
        if (status === "ADDED") {
            accent = "#55c98a"; bg = "rgba(40,150,90,.11)"; badgeBg = "rgba(40,150,90,.22)"; badgeText = "#9be7b8";
        } else if (status === "REMOVED") {
            accent = "#ee7278"; bg = "rgba(190,55,65,.11)"; badgeBg = "rgba(190,55,65,.22)"; badgeText = "#ffaaaa";
        } else if (status === "CHANGED") {
            accent = "#8ab4f8"; bg = "rgba(70,120,200,.09)"; badgeBg = "rgba(70,120,200,.2)"; badgeText = "#c7dcff";
        }

        const card = document.createElement("div");
        card.style.cssText = "border-left:3px solid " + accent + ";background:" + bg + ";border-radius:4px;padding:7px 8px;margin:0 0 7px 0;";

        const heading = document.createElement("div");
        heading.style.cssText = "display:flex;align-items:flex-start;gap:7px;margin-bottom:5px;";
        const badge = document.createElement("span");
        badge.textContent = status;
        badge.style.cssText = "flex:0 0 auto;font:bold 9px/1.5 sans-serif;letter-spacing:.4px;padding:2px 5px;border-radius:3px;background:" + badgeBg + ";color:" + badgeText + ";";
        const name = document.createElement("span");
        name.textContent = label;
        name.style.cssText = "font:12px/1.4 sans-serif;color:#d7dce2;overflow-wrap:anywhere;";
        heading.append(badge, name);
        card.appendChild(heading);

        for (const line of blockLines) {
            const valueLine = document.createElement("div");
            const trimmed = line.trimStart();
            let color = "#aeb5bf", lineBg = "transparent", shown = line;
            if (/^-\s?/.test(trimmed)) {
                shown = "− " + trimmed.replace(/^-\s?/, "");
                color = "#ff9a9a"; lineBg = "rgba(190,55,65,.13)";
            } else if (/^\+\s?/.test(trimmed)) {
                shown = "+ " + trimmed.replace(/^\+\s?/, "");
                color = "#8fe0ad"; lineBg = "rgba(40,150,90,.13)";
            }
            valueLine.textContent = shown;
            valueLine.style.cssText = "white-space:pre-wrap;overflow-wrap:anywhere;padding:2px 5px;margin:2px 0;border-radius:3px;font:12px/1.45 monospace;color:" + color + ";background:" + lineBg + ";";
            card.appendChild(valueLine);
        }
        panel.appendChild(card);
    }

    const summary = document.createElement("div");
    summary.textContent = added + " added  ·  " + removed + " removed  ·  " + changed + " changed";
    summary.style.cssText = "padding:7px 2px 2px;color:#9aa3ad;font:11px sans-serif;text-align:right;";
    panel.appendChild(summary);
}

// Browser file pickers for Video Prompt Diff. Videos are uploaded to ComfyUI/input,
// so this also works when the browser is connected to a remote ComfyUI server.
app.registerExtension({
    name: "Crystools.VideoPromptDiff.FilePicker",
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "Video Prompt Diff [Crystools]") return;

        const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
        const originalOnExecuted = nodeType.prototype.onExecuted;

        nodeType.prototype.onExecuted = function (message) {
            const result = originalOnExecuted?.apply(this, arguments);
            const panel = this.__crystoolsDiffPanel;
            if (panel) {
                const text = Array.isArray(message?.text) ? message.text.join("\n")
                    : (message?.text == null ? "" : String(message.text));
                renderVideoDiff(panel, text);
                this.setSize?.(this.computeSize());
                this.setDirtyCanvas?.(true, true);
                app.graph?.setDirtyCanvas?.(true, true);
            }
            return result;
        };

        nodeType.prototype.onNodeCreated = function () {
            const result = originalOnNodeCreated?.apply(this, arguments);
            const node = this;

            const panel = document.createElement("div");
            panel.className = "crystools-video-diff-panel";
            panel.style.cssText = [
                "box-sizing:border-box", "width:100%", "min-height:86px",
                "max-height:390px", "overflow-y:auto", "overflow-x:hidden",
                "padding:10px", "border-radius:6px",
                "background:var(--comfy-input-bg,#222)",
                "color:var(--input-text,#ddd)",
                "font:12px/1.45 monospace", "white-space:normal",
                "overflow-wrap:anywhere", "border:1px solid var(--border-color,#454545)"
            ].join(";");
            panel.textContent = "Queue this node to compare the selected videos.";
            this.__crystoolsDiffPanel = panel;

            if (typeof this.addDOMWidget === "function") {
                this.addDOMWidget("Video Diff Results", "div", panel, {
                    serialize: false,
                    hideOnZoom: false,
                    getHeight: () => Math.min(410, Math.max(86, panel.scrollHeight + 2)),
                });
            } else {
                console.warn("[Crystools Video Prompt Diff] addDOMWidget unavailable; colored panel disabled.");
            }

            const chooseVideo = (widgetName, label) => {
                const picker = document.createElement("input");
                picker.type = "file";
                picker.accept = ".mp4,.mov,.mkv,.webm,.m4v,.avi,video/mp4,video/quicktime,video/webm";
                picker.style.display = "none";

                picker.addEventListener("change", async () => {
                    const file = picker.files?.[0];
                    if (!file) {
                        picker.remove();
                        return;
                    }

                    try {
                        console.info("[Crystools Video Prompt Diff DEBUG] selected local file", {
                            name: file.name, size: file.size, type: file.type,
                            note: "Browser does not expose the original absolute Windows path; this file will be copied to the ComfyUI server."
                        });
                        const form = new FormData();
                        form.append("image", file, file.name);
                        form.append("type", "input");
                        form.append("subfolder", "crystools_video_diff");
                        form.append("overwrite", "false");

                        console.info("[Crystools Video Prompt Diff DEBUG] uploading to ComfyUI input subfolder crystools_video_diff");
                        const response = await fetch("/upload/image", {
                            method: "POST",
                            body: form,
                        });
                        console.info("[Crystools Video Prompt Diff DEBUG] upload response status", response.status);
                        if (!response.ok) {
                            const details = await response.text();
                            throw new Error("ComfyUI upload failed (" + response.status + "): " + details);
                        }

                        const uploaded = await response.json();
                        console.info("[Crystools Video Prompt Diff DEBUG] server upload result", uploaded);
                        const widget = node.widgets?.find((w) => w.name === widgetName);
                        if (!widget) throw new Error("Could not find node field: " + widgetName);

                        widget.value = [uploaded.subfolder, uploaded.name].filter(Boolean).join("/");
                        console.info("[Crystools Video Prompt Diff DEBUG] field set to server-relative path", widget.value);
                        if (typeof widget.callback === "function") {
                            widget.callback(widget.value, app.canvas, node);
                        }
                        node.setDirtyCanvas?.(true, true);
                        app.graph?.setDirtyCanvas?.(true, true);
                    } catch (error) {
                        console.error("[Crystools Video Prompt Diff] Upload failed", error);
                        window.alert(label + " failed:\n" + (error?.message || String(error)));
                    } finally {
                        picker.remove();
                    }
                });
                picker.addEventListener("cancel", () => picker.remove(), { once: true });
                document.body.appendChild(picker);
                picker.click();
            };

            // Add both buttons after the text fields, so the selected uploaded path
            // remains visible and can also be manually edited.
            node.addWidget("button", "Browse video A…", null, () => chooseVideo("video_a", "Browse video A"));
            node.addWidget("button", "Browse video B…", null, () => chooseVideo("video_b", "Browse video B"));
            node.setDirtyCanvas?.(true, true);
            return result;
        };
    },
});
