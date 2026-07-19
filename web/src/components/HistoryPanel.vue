<script setup lang="ts">
import { useStudioStore } from "../stores/studio";
import type { HistoryEntry } from "../types";

const studio = useStudioStore();

function title(entry: HistoryEntry): string {
  return entry.question || entry.sql.split("\n")[0] || "Untitled query";
}

function relative(value: string): string {
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000));
  if (seconds < 60) return "now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
  return `${Math.floor(seconds / 86400)}d`;
}
</script>

<template>
  <div class="history-panel">
    <div class="history-search">
      <span>⌕</span>
      <input
        v-model="studio.historySearch"
        aria-label="Search query history"
        placeholder="Search history"
        @keydown.enter="studio.loadHistory()"
      />
      <button v-if="studio.historySearch" @click="studio.historySearch = ''; studio.loadHistory()">×</button>
    </div>
    <div class="history-list">
      <article
        v-for="entry in studio.history"
        :key="entry.id"
        :class="['history-entry', { active: studio.activeHistoryId === entry.id }]"
        role="button"
        tabindex="0"
        @click="studio.restoreHistory(entry)"
        @keydown.enter="studio.restoreHistory(entry)"
      >
        <div class="history-entry-title"><span v-if="entry.pinned">◆</span>{{ title(entry) }}</div>
        <code>{{ entry.sql }}</code>
        <footer>
          <span :class="['history-status', entry.status]" />
          <span>{{ entry.connection }}</span><span>·</span><span>{{ relative(entry.updated_at) }}</span>
          <div>
            <button :title="entry.pinned ? 'Unpin' : 'Pin'" @click.stop="studio.toggleHistoryPin(entry)">{{ entry.pinned ? "◇" : "◆" }}</button>
            <button title="Delete" @click.stop="studio.removeHistory(entry)">×</button>
          </div>
        </footer>
      </article>
      <div v-if="!studio.history.length" class="empty-small">No query history yet</div>
    </div>
  </div>
</template>
