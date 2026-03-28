/**
 * Типы для Yandex Wordstat API
 */
export interface WordstatConfig {
    token: string;
    baseUrl?: string;
}
export interface TopRequestsParams {
    phrase: string;
    numPhrases?: number;
    regions?: number[];
    devices?: DeviceType[];
}
export interface DynamicsParams {
    phrase: string;
    period: PeriodType;
    fromDate: string;
    toDate?: string;
    regions?: number[];
    devices?: DeviceType[];
}
export interface RegionsParams {
    phrase: string;
    regionType?: RegionFilterType;
    devices?: DeviceType[];
}
export type DeviceType = 'all' | 'desktop' | 'phone' | 'tablet';
export type PeriodType = 'daily' | 'weekly' | 'monthly';
export type RegionFilterType = 'all' | 'cities' | 'regions';
export interface TopRequestsResponse {
    requestPhrase: string;
    totalCount: number;
    topRequests: PhraseCount[];
    associations: PhraseCount[];
}
export interface PhraseCount {
    phrase: string;
    count: number;
}
export interface DynamicsResponse {
    requestPhrase: string;
    dynamics: DynamicsPoint[];
}
export interface DynamicsPoint {
    date: string;
    count: number;
    share: number;
}
export interface RegionsResponse {
    requestPhrase: string;
    regions: RegionData[];
}
export interface RegionData {
    regionId: number;
    count: number;
    share: number;
    affinityIndex: number;
}
export interface UserInfoResponse {
    userInfo: {
        login: string;
        limitPerSecond: number;
        dailyLimit: number;
        dailyLimitRemaining: number;
    };
}
export interface RegionTreeNode {
    value: string;
    label: string;
    children: RegionTreeNode[] | null;
}
export interface WordstatError {
    error: string;
    message: string;
}
