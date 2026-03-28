#!/usr/bin/env node
/**
 * MCP Server для Yandex Wordstat API
 *
 * Предоставляет 5 инструментов для анализа поисковых запросов:
 * - wordstat_top_requests: топ популярных запросов по фразе
 * - wordstat_dynamics: динамика запросов во времени
 * - wordstat_regions: распределение по регионам
 * - wordstat_regions_tree: дерево всех регионов
 * - wordstat_user_info: информация о квоте
 *
 * НОВОЕ: Все инструменты поддерживают параметр outputDir для автоматического
 * сохранения результатов в файлы (не возвращая их в контекст)
 */
export {};
