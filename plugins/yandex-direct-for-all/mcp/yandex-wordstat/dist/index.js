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
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { CallToolRequestSchema, ListToolsRequestSchema, ErrorCode, McpError } from "@modelcontextprotocol/sdk/types.js";
import * as fs from 'fs';
import * as path from 'path';
import { WordstatClient } from './client.js';
import { topRequestsSchema, dynamicsSchema, regionsSchema } from './schemas.js';
// === Конфигурация ===
const TOKEN = process.env.YANDEX_WORDSTAT_TOKEN;
if (!TOKEN) {
    console.error('ОШИБКА: Переменная YANDEX_WORDSTAT_TOKEN не установлена.');
    console.error('Добавьте токен в env секцию конфигурации MCP-сервера в ~/.claude.json');
    process.exit(1);
}
const client = new WordstatClient({ token: TOKEN });
// === Утилита для сохранения в файл ===
function saveToFile(outputDir, phrase, toolName, data) {
    // Создаём директорию если не существует
    if (!fs.existsSync(outputDir)) {
        fs.mkdirSync(outputDir, { recursive: true });
    }
    // Очищаем фразу для имени файла
    const safeName = phrase
        .replace(/[^a-zA-Zа-яА-ЯёЁ0-9\s]/g, '')
        .replace(/\s+/g, '_')
        .substring(0, 50);
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').substring(0, 19);
    const fileName = `${toolName}_${safeName}_${timestamp}.json`;
    const filePath = path.join(outputDir, fileName);
    fs.writeFileSync(filePath, JSON.stringify(data, null, 2), 'utf-8');
    return filePath;
}
// === Создание сервера ===
const server = new Server({
    name: "yandex-wordstat",
    version: "1.1.0"
}, {
    capabilities: {
        tools: {}
    }
});
// === Определение инструментов ===
server.setRequestHandler(ListToolsRequestSchema, async () => ({
    tools: [
        {
            name: "wordstat_top_requests",
            description: `Получить топ популярных поисковых запросов по фразе из Яндекс Вордстат.

Возвращает:
- totalCount: общее число показов за месяц
- topRequests: список вложенных запросов с частотой
- associations: связанные запросы (похожие темы)

ВАЖНО: Используй параметр outputDir чтобы сохранить результаты в файл!
Расходует 1 единицу квоты. Лимит: 1024 запроса/день.`,
            inputSchema: {
                type: "object",
                properties: {
                    phrase: {
                        type: "string",
                        description: "Поисковая фраза (например: 'купить телефон')"
                    },
                    numPhrases: {
                        type: "number",
                        description: "Количество результатов (1-2000, по умолчанию 10)"
                    },
                    regions: {
                        type: "array",
                        items: { type: "number" },
                        description: "ID регионов (получить через wordstat_regions_tree)"
                    },
                    devices: {
                        type: "array",
                        items: { type: "string", enum: ["all", "desktop", "phone", "tablet"] },
                        description: "Фильтр по устройствам"
                    },
                    outputDir: {
                        type: "string",
                        description: "ОБЯЗАТЕЛЬНО! Путь к директории для сохранения результатов (файл не вернётся в контекст)"
                    }
                },
                required: ["phrase"]
            }
        },
        {
            name: "wordstat_dynamics",
            description: `Получить динамику поискового запроса во времени.

Периоды:
- daily: данные по дням (максимум 60 дней)
- weekly: по неделям (fromDate = воскресенье!)
- monthly: по месяцам (fromDate = 1-е число!)

Возвращает массив точек с date, count, share.
ВАЖНО: Используй параметр outputDir чтобы сохранить результаты в файл!
Расходует 1 единицу квоты.`,
            inputSchema: {
                type: "object",
                properties: {
                    phrase: {
                        type: "string",
                        description: "Поисковая фраза"
                    },
                    period: {
                        type: "string",
                        enum: ["daily", "weekly", "monthly"],
                        description: "Период агрегации"
                    },
                    fromDate: {
                        type: "string",
                        description: "Начало периода YYYY-MM-DD (для weekly - воскресенье, для monthly - 1-е число)"
                    },
                    toDate: {
                        type: "string",
                        description: "Конец периода YYYY-MM-DD (опционально)"
                    },
                    regions: {
                        type: "array",
                        items: { type: "number" },
                        description: "ID регионов"
                    },
                    devices: {
                        type: "array",
                        items: { type: "string", enum: ["all", "desktop", "phone", "tablet"] }
                    },
                    outputDir: {
                        type: "string",
                        description: "ОБЯЗАТЕЛЬНО! Путь к директории для сохранения результатов"
                    }
                },
                required: ["phrase", "period", "fromDate"]
            }
        },
        {
            name: "wordstat_regions",
            description: `Получить географическое распределение запроса по регионам России.

Возвращает для каждого региона:
- count: абсолютное число запросов
- share: доля от всех запросов
- affinityIndex: индекс соответствия (>100 = выше среднего)

ВАЖНО: Используй параметр outputDir чтобы сохранить результаты в файл!
Расходует 2 единицы квоты!`,
            inputSchema: {
                type: "object",
                properties: {
                    phrase: {
                        type: "string",
                        description: "Поисковая фраза"
                    },
                    regionType: {
                        type: "string",
                        enum: ["all", "cities", "regions"],
                        description: "Фильтр: all (всё), cities (города), regions (регионы)"
                    },
                    devices: {
                        type: "array",
                        items: { type: "string", enum: ["all", "desktop", "phone", "tablet"] }
                    },
                    outputDir: {
                        type: "string",
                        description: "ОБЯЗАТЕЛЬНО! Путь к директории для сохранения результатов"
                    }
                },
                required: ["phrase"]
            }
        },
        {
            name: "wordstat_regions_tree",
            description: `Получить полное дерево регионов Яндекса с ID и названиями.

Используй для получения ID регионов перед фильтрацией в других инструментах.
НЕ расходует квоту - можно вызывать без ограничений.

Структура: Россия → Федеральные округа → Области → Города`,
            inputSchema: {
                type: "object",
                properties: {
                    outputDir: {
                        type: "string",
                        description: "Путь к директории для сохранения результатов (опционально)"
                    }
                }
            }
        },
        {
            name: "wordstat_user_info",
            description: `Проверить текущую квоту и лимиты API.

Возвращает:
- login: имя аккаунта
- limitPerSecond: лимит запросов в секунду
- dailyLimit: дневной лимит
- dailyLimitRemaining: осталось запросов сегодня

НЕ расходует квоту. Вызывай перед массовыми операциями!`,
            inputSchema: {
                type: "object",
                properties: {}
            }
        }
    ]
}));
// === Обработка вызовов инструментов ===
server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const { name, arguments: args } = request.params;
    try {
        let result;
        let phrase = '';
        let outputDir;
        switch (name) {
            case "wordstat_top_requests": {
                const parsed = topRequestsSchema.parse(args);
                phrase = parsed.phrase;
                outputDir = parsed.outputDir;
                // Убираем outputDir перед отправкой в API
                const { outputDir: _, ...apiParams } = parsed;
                result = await client.getTopRequests(apiParams);
                break;
            }
            case "wordstat_dynamics": {
                const parsed = dynamicsSchema.parse(args);
                phrase = parsed.phrase;
                outputDir = parsed.outputDir;
                // Убираем outputDir перед отправкой в API
                const { outputDir: _, ...apiParams } = parsed;
                result = await client.getDynamics(apiParams);
                break;
            }
            case "wordstat_regions": {
                const parsed = regionsSchema.parse(args);
                phrase = parsed.phrase;
                outputDir = parsed.outputDir;
                // Убираем outputDir перед отправкой в API
                const { outputDir: _, ...apiParams } = parsed;
                result = await client.getRegions(apiParams);
                break;
            }
            case "wordstat_regions_tree": {
                phrase = 'regions_tree';
                const rawArgs = args;
                outputDir = rawArgs?.outputDir;
                result = await client.getRegionsTree();
                break;
            }
            case "wordstat_user_info": {
                result = await client.getUserInfo();
                // Для user_info всегда возвращаем в контекст (маленький ответ)
                return {
                    content: [{
                            type: "text",
                            text: JSON.stringify(result, null, 2)
                        }]
                };
            }
            default:
                throw new McpError(ErrorCode.MethodNotFound, `Неизвестный инструмент: ${name}. Доступные: wordstat_top_requests, wordstat_dynamics, wordstat_regions, wordstat_regions_tree, wordstat_user_info`);
        }
        // Если указан outputDir - сохраняем в файл
        if (outputDir) {
            const filePath = saveToFile(outputDir, phrase, name, result);
            // Краткая статистика для ответа
            let stats = '';
            if (name === 'wordstat_top_requests') {
                const r = result;
                stats = `Найдено: ${r.topRequests?.length || 0} ключей, общая частота: ${r.totalCount?.toLocaleString() || 0}`;
            }
            else if (name === 'wordstat_dynamics') {
                const r = result;
                stats = `Найдено: ${r.dynamics?.length || 0} точек данных`;
            }
            else if (name === 'wordstat_regions') {
                const r = result;
                stats = `Найдено: ${r.regions?.length || 0} регионов`;
            }
            else if (name === 'wordstat_regions_tree') {
                stats = 'Дерево регионов сохранено';
            }
            return {
                content: [{
                        type: "text",
                        text: `✅ Сохранено в файл: ${filePath}\n${stats}`
                    }]
            };
        }
        // Без outputDir - возвращаем как раньше (в контекст)
        return {
            content: [{
                    type: "text",
                    text: JSON.stringify(result, null, 2)
                }]
        };
    }
    catch (error) {
        // Zod validation error
        if (error && typeof error === 'object' && 'issues' in error) {
            const zodError = error;
            const messages = zodError.issues.map(i => `${i.path.join('.')}: ${i.message}`).join('; ');
            return {
                content: [{
                        type: "text",
                        text: `Ошибка валидации параметров: ${messages}`
                    }],
                isError: true
            };
        }
        // API or other errors
        const message = error instanceof Error ? error.message : String(error);
        return {
            content: [{
                    type: "text",
                    text: `Ошибка: ${message}`
                }],
            isError: true
        };
    }
});
// === Запуск сервера ===
async function main() {
    const transport = new StdioServerTransport();
    await server.connect(transport);
    console.error("Yandex Wordstat MCP Server v1.1.0 запущен (с поддержкой сохранения в файлы)");
}
main().catch((error) => {
    console.error("Критическая ошибка:", error);
    process.exit(1);
});
