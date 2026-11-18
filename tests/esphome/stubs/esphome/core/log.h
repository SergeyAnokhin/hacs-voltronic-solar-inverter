#pragma once
#include <cstdio>
#define ESP_LOGE(tag, ...) (printf("[E][%s] ", tag), printf(__VA_ARGS__), printf("\n"))
#define ESP_LOGW(tag, ...) (printf("[W][%s] ", tag), printf(__VA_ARGS__), printf("\n"))
#define ESP_LOGI(tag, ...) (printf("[I][%s] ", tag), printf(__VA_ARGS__), printf("\n"))
#define ESP_LOGD(tag, ...) ((void)0)
#define ESP_LOGV(tag, ...) ((void)0)
#define ESP_LOGCONFIG(tag, ...) ((void)0)
