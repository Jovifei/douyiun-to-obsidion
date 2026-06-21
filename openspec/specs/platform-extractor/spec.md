## ADDED Requirements

### Requirement: 平台通用 extractor 接口

系统 SHALL 定义 `PlatformExtractor` ABC，所有平台 extractor 实现统一接口。

#### Scenario: 抖音 extractor 实现 PlatformExtractor

- **WHEN** 调用 `resolve_url("https://v.douyin.com/xxx/")`
- **THEN** 返回 dict 含 `video_id`、`canonical_url`、`platform="douyin"`

#### Scenario: Bilibili extractor 实现 PlatformExtractor

- **WHEN** 调用 `resolve_url("https://b23.tv/xxx")`
- **THEN** 返回 dict 含 `video_id`、`canonical_url`、`platform="bilibili"`

#### Scenario: 工厂路由

- **WHEN** 调用 `get_extractor("douyin", config)`
- **THEN** 返回 DouyinExtractor 实例（PlatformExtractor 子类）
