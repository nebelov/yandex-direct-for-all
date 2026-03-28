/**
 * Zod-схемы для валидации параметров MCP tools
 */
import { z } from 'zod';
export declare const topRequestsSchema: z.ZodObject<{
    phrase: z.ZodString;
    numPhrases: z.ZodOptional<z.ZodNumber>;
    regions: z.ZodOptional<z.ZodArray<z.ZodNumber, "many">>;
    devices: z.ZodOptional<z.ZodArray<z.ZodEnum<["all", "desktop", "phone", "tablet"]>, "many">>;
    outputDir: z.ZodOptional<z.ZodString>;
}, "strip", z.ZodTypeAny, {
    phrase: string;
    regions?: number[] | undefined;
    numPhrases?: number | undefined;
    devices?: ("all" | "desktop" | "phone" | "tablet")[] | undefined;
    outputDir?: string | undefined;
}, {
    phrase: string;
    regions?: number[] | undefined;
    numPhrases?: number | undefined;
    devices?: ("all" | "desktop" | "phone" | "tablet")[] | undefined;
    outputDir?: string | undefined;
}>;
export declare const dynamicsSchema: z.ZodObject<{
    phrase: z.ZodString;
    period: z.ZodEnum<["daily", "weekly", "monthly"]>;
    fromDate: z.ZodString;
    toDate: z.ZodOptional<z.ZodString>;
    regions: z.ZodOptional<z.ZodArray<z.ZodNumber, "many">>;
    devices: z.ZodOptional<z.ZodArray<z.ZodEnum<["all", "desktop", "phone", "tablet"]>, "many">>;
    outputDir: z.ZodOptional<z.ZodString>;
}, "strip", z.ZodTypeAny, {
    phrase: string;
    period: "daily" | "weekly" | "monthly";
    fromDate: string;
    regions?: number[] | undefined;
    devices?: ("all" | "desktop" | "phone" | "tablet")[] | undefined;
    outputDir?: string | undefined;
    toDate?: string | undefined;
}, {
    phrase: string;
    period: "daily" | "weekly" | "monthly";
    fromDate: string;
    regions?: number[] | undefined;
    devices?: ("all" | "desktop" | "phone" | "tablet")[] | undefined;
    outputDir?: string | undefined;
    toDate?: string | undefined;
}>;
export declare const regionsSchema: z.ZodObject<{
    phrase: z.ZodString;
    regionType: z.ZodOptional<z.ZodEnum<["all", "cities", "regions"]>>;
    devices: z.ZodOptional<z.ZodArray<z.ZodEnum<["all", "desktop", "phone", "tablet"]>, "many">>;
    outputDir: z.ZodOptional<z.ZodString>;
}, "strip", z.ZodTypeAny, {
    phrase: string;
    devices?: ("all" | "desktop" | "phone" | "tablet")[] | undefined;
    outputDir?: string | undefined;
    regionType?: "all" | "cities" | "regions" | undefined;
}, {
    phrase: string;
    devices?: ("all" | "desktop" | "phone" | "tablet")[] | undefined;
    outputDir?: string | undefined;
    regionType?: "all" | "cities" | "regions" | undefined;
}>;
export declare const emptySchema: z.ZodObject<{
    outputDir: z.ZodOptional<z.ZodString>;
}, "strip", z.ZodTypeAny, {
    outputDir?: string | undefined;
}, {
    outputDir?: string | undefined;
}>;
export type TopRequestsInput = z.infer<typeof topRequestsSchema>;
export type DynamicsInput = z.infer<typeof dynamicsSchema>;
export type RegionsInput = z.infer<typeof regionsSchema>;
