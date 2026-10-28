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


// Browser file pickers for Video Prompt Diff. Videos are uploaded to ComfyUI/input,
// so this also works when the browser is connected to a remote ComfyUI server.
app.registerExtension({
    name: "Crystools.VideoPromptDiff.FilePicker",
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "Video Prompt Diff [Crystools]") return;

        const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = originalOnNodeCreated?.apply(this, arguments);
            const node = this;

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
