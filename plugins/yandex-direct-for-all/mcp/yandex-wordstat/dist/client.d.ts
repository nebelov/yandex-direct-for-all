/**
 * HTTP-клиент для Yandex Wordstat API
 */
import { WordstatConfig, TopRequestsParams, DynamicsParams, RegionsParams, TopRequestsResponse, DynamicsResponse, RegionsResponse, UserInfoResponse, RegionTreeNode } from './types.js';
export declare class WordstatClient {
    private token;
    private baseUrl;
    constructor(config: WordstatConfig);
    private request;
    /**
     * Получить дерево всех регионов Яндекса
     * НЕ расходует квоту
     */
    getRegionsTree(): Promise<RegionTreeNode[]>;
    /**
     * Получить топ популярных запросов по фразе
     * Расходует 1 единицу квоты
     */
    getTopRequests(params: TopRequestsParams): Promise<TopRequestsResponse>;
    /**
     * Получить динамику запросов во времени
     * Расходует 1 единицу квоты
     *
     * ВАЖНО: для period='weekly' fromDate должен быть воскресеньем,
     *        для period='monthly' fromDate должен быть 1-м числом месяца
     */
    getDynamics(params: DynamicsParams): Promise<DynamicsResponse>;
    /**
     * Получить распределение запросов по регионам
     * Расходует 2 единицы квоты
     */
    getRegions(params: RegionsParams): Promise<RegionsResponse>;
    /**
     * Получить информацию о квоте пользователя
     * НЕ расходует квоту
     */
    getUserInfo(): Promise<UserInfoResponse>;
}
