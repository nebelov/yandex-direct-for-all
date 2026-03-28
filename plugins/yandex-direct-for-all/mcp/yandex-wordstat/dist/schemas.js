/**
 * Zod-схемы для валидации параметров MCP tools
 */
import { z } from 'zod';
const deviceEnum = z.enum(['all', 'desktop', 'phone', 'tablet']);
export const topRequestsSchema = z.object({
    phrase: z.string()
        .min(1, 'Фраза не может быть пустой')
        .describe('Поисковая фраза для анализа (например: "купить телефон")'),
    numPhrases: z.number()
        .min(1)
        .max(2000)
        .optional()
        .describe('Количество результатов (по умолчанию 10, максимум 2000)'),
    regions: z.array(z.number())
        .optional()
        .describe('ID регионов для фильтрации (получить из wordstat_regions_tree)'),
    devices: z.array(deviceEnum)
        .optional()
        .describe('Типы устройств: all, desktop, phone, tablet'),
    outputDir: z.string()
        .optional()
        .describe('Путь к директории для сохранения результатов')
});
export const dynamicsSchema = z.object({
    phrase: z.string()
        .min(1, 'Фраза не может быть пустой')
        .describe('Поисковая фраза для анализа динамики'),
    period: z.enum(['daily', 'weekly', 'monthly'])
        .describe('Период агрегации: daily (до 60 дней), weekly, monthly'),
    fromDate: z.string()
        .regex(/^\d{4}-\d{2}-\d{2}$/, 'Формат даты: YYYY-MM-DD')
        .describe('Начало периода (YYYY-MM-DD). Для weekly - воскресенье, для monthly - 1-е число'),
    toDate: z.string()
        .regex(/^\d{4}-\d{2}-\d{2}$/, 'Формат даты: YYYY-MM-DD')
        .optional()
        .describe('Конец периода (YYYY-MM-DD). По умолчанию - сегодня'),
    regions: z.array(z.number())
        .optional()
        .describe('ID регионов для фильтрации'),
    devices: z.array(deviceEnum)
        .optional()
        .describe('Типы устройств для фильтрации'),
    outputDir: z.string()
        .optional()
        .describe('Путь к директории для сохранения результатов')
});
export const regionsSchema = z.object({
    phrase: z.string()
        .min(1, 'Фраза не может быть пустой')
        .describe('Поисковая фраза для географического анализа'),
    regionType: z.enum(['all', 'cities', 'regions'])
        .optional()
        .describe('Фильтр по типу региона: all (все), cities (города), regions (регионы)'),
    devices: z.array(deviceEnum)
        .optional()
        .describe('Типы устройств для фильтрации'),
    outputDir: z.string()
        .optional()
        .describe('Путь к директории для сохранения результатов')
});
// Схемы для tools без параметров
export const emptySchema = z.object({
    outputDir: z.string()
        .optional()
        .describe('Путь к директории для сохранения результатов')
});
