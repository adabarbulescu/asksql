<script setup lang="ts">
import { useStudioStore } from "../stores/studio";

const studio = useStudioStore();
</script>

<template>
  <section class="saved-library">
    <div class="library-search">
      <span>⌕</span>
      <input v-model="studio.librarySearch" placeholder="Search saved queries" @input="studio.loadSavedQueries()" />
    </div>
    <div class="library-filters">
      <select v-model="studio.libraryFolder" @change="studio.loadSavedQueries()">
        <option :value="undefined">All folders</option>
        <option value="">Unfiled</option>
        <option v-for="folder in studio.savedQueryFolders" :key="folder" :value="folder">{{ folder }}</option>
      </select>
      <select v-model="studio.libraryTag" @change="studio.loadSavedQueries()">
        <option :value="undefined">All tags</option>
        <option v-for="tag in studio.savedQueryTags" :key="tag" :value="tag">#{{ tag }}</option>
      </select>
      <button :class="{ active: studio.libraryFavoritesOnly }" title="Favorites only" @click="studio.libraryFavoritesOnly = !studio.libraryFavoritesOnly; studio.loadSavedQueries()">★</button>
    </div>
    <div class="saved-query-list">
      <article v-for="item in studio.savedQueries" :key="item.id" class="saved-query-card">
        <header>
          <button class="favorite-query" :class="{ active: item.favorite }" @click="studio.toggleSavedQueryFavorite(item)">★</button>
          <button class="saved-query-name" @click="studio.openSavedQuery(item)">{{ item.name }}</button>
        </header>
        <p v-if="item.description">{{ item.description }}</p>
        <code>{{ item.sql }}</code>
        <div class="saved-query-meta"><span>{{ item.folder || "Unfiled" }}</span><span>{{ item.connection_hint }}</span></div>
        <div v-if="item.tags.length" class="saved-query-tags"><span v-for="tag in item.tags" :key="tag">#{{ tag }}</span></div>
        <footer>
          <button @click="studio.openSavedQuery(item)">Open</button>
          <button @click="studio.duplicateSavedQueryItem(item)">Duplicate</button>
          <button class="delete-saved" @click="studio.removeSavedQueryItem(item)">Delete</button>
        </footer>
      </article>
      <div v-if="!studio.savedQueries.length" class="library-empty">No reusable queries match these filters.</div>
    </div>
  </section>
</template>
