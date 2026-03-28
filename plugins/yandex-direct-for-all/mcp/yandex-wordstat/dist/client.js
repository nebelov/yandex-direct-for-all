/**
 * HTTP-клиент для Yandex Wordstat API
 */
const DEFAULT_BASE_URL = 'https://api.wordstat.yandex.net';
export class WordstatClient {
    token;
    baseUrl;
    constructor(config) {
        this.token = config.token;
        this.baseUrl = config.baseUrl || DEFAULT_BASE_URL;
    }
    async request(endpoint, body = {}) {
        const url = `${this.baseUrl}${endpoint}`;
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${this.token}`
            },
            body: JSON.stringify(body)
        });
        const text = await response.text();
        if (!response.ok) {
            // Формируем понятное сообщение для AI-агента
            throw new Error(`API error ${response.status}: ${text}. ` +
                `Действие: проверьте токен и параметры запроса.`);
        }
        try {
            return JSON.parse(text);
        }
        catch {
            throw new Error(`Invalid JSON response: ${text.substring(0, 200)}`);
        }
    }
    /**
     * Получить дерево всех регионов Яндекса
     * НЕ расходует квоту
     */
    async getRegionsTree() {
        return this.request('/v1/getRegionsTree');
    }
    /**
     * Получить топ популярных запросов по фразе
     * Расходует 1 единицу квоты
     */
    async getTopRequests(params) {
        return this.request('/v1/topRequests', params);
    }
    /**
     * Получить динамику запросов во времени
     * Расходует 1 единицу квоты
     *
     * ВАЖНО: для period='weekly' fromDate должен быть воскресеньем,
     *        для period='monthly' fromDate должен быть 1-м числом месяца
     */
    async getDynamics(params) {
        return this.request('/v1/dynamics', params);
    }
    /**
     * Получить распределение запросов по регионам
     * Расходует 2 единицы квоты
     */
    async getRegions(params) {
        return this.request('/v1/regions', params);
    }
    /**
     * Получить информацию о квоте пользователя
     * НЕ расходует квоту
     */
    async getUserInfo() {
        return this.request('/v1/userInfo');
    }
}
