<script setup lang="ts">
import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { sql } from "@codemirror/lang-sql";
import { EditorState } from "@codemirror/state";
import { EditorView, keymap, lineNumbers } from "@codemirror/view";
import { onBeforeUnmount, onMounted, ref, watch } from "vue";

const props = defineProps<{ modelValue: string }>();
const emit = defineEmits<{ "update:modelValue": [value: string] }>();
const root = ref<HTMLElement>();
let view: EditorView | undefined;

const theme = EditorView.theme({
  "&": { height: "100%", color: "#e8eaf0", backgroundColor: "#0d1017" },
  ".cm-content": { caretColor: "#8b7cff", fontFamily: "var(--font-mono)", padding: "16px 0" },
  ".cm-cursor": { borderLeftColor: "#8b7cff" },
  ".cm-gutters": { backgroundColor: "#0d1017", color: "#4e5564", border: "none" },
  ".cm-activeLine, .cm-activeLineGutter": { backgroundColor: "#141824" },
  ".cm-selectionBackground": { backgroundColor: "#393064 !important" },
  ".tok-keyword": { color: "#b8a9ff" },
  ".tok-string": { color: "#80d4ba" },
  ".tok-number": { color: "#f0b879" },
});

onMounted(() => {
  view = new EditorView({
    parent: root.value,
    state: EditorState.create({
      doc: props.modelValue,
      extensions: [
        lineNumbers(),
        history(),
        sql(),
        theme,
        keymap.of([...defaultKeymap, ...historyKeymap]),
        EditorView.lineWrapping,
        EditorView.updateListener.of((update) => {
          if (update.docChanged) emit("update:modelValue", update.state.doc.toString());
        }),
      ],
    }),
  });
});

watch(
  () => props.modelValue,
  (value) => {
    if (!view || value === view.state.doc.toString()) return;
    view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: value } });
  },
);

onBeforeUnmount(() => view?.destroy());
</script>

<template><div ref="root" class="sql-editor" /></template>
