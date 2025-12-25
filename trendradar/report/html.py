# coding=utf-8
"""
HTML 报告渲染模块

提供 HTML 格式的热点新闻报告生成功能
"""

from datetime import datetime
from typing import Dict, Optional, Callable

from trendradar.report.helpers import html_escape


def render_html_content(
    report_data: Dict,
    total_titles: int,
    is_daily_summary: bool = False,
    mode: str = "daily",
    update_info: Optional[Dict] = None,
    *,
    reverse_content_order: bool = False,
    get_time_func: Optional[Callable[[], datetime]] = None,
) -> str:
    """渲染HTML内容

    Args:
        report_data: 报告数据字典，包含 stats, new_titles, failed_ids, total_new_count
        total_titles: 新闻总数
        is_daily_summary: 是否为当日汇总
        mode: 报告模式 ("daily", "current", "incremental")
        update_info: 更新信息（可选）
        reverse_content_order: 是否反转内容顺序（新增热点在前）
        get_time_func: 获取当前时间的函数（可选，默认使用 datetime.now）

    Returns:
        渲染后的 HTML 字符串
    """
    # 预计算头部信息（让头部更紧凑、避免在 HTML 拼接中穿插过多逻辑）
    if is_daily_summary:
        if mode == "current":
            report_type_label = "当前榜单"
        elif mode == "incremental":
            report_type_label = "增量模式"
        else:
            report_type_label = "当日汇总"
    else:
        report_type_label = "实时分析"

    now = get_time_func() if get_time_func else datetime.now()
    now_label = now.strftime("%m-%d %H:%M")
    hot_news_count = sum(
        len(stat.get("titles", [])) for stat in report_data.get("stats", [])
    )

    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>热点新闻分析</title>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js" integrity="sha512-BNaRQnYJYiPSqHHDb58B0yaPfCu+Wgds8Gp/gU33kqBtgNS4tSPHuGibyoeqMV/TJlSKda6FXzoEyYGjTe+vXA==" crossorigin="anonymous" referrerpolicy="no-referrer"></script>
        <style>
            :root {
                color-scheme: dark;
                --bg: #0b1020;
                --card: rgba(255,255,255,0.06);
                --card2: rgba(255,255,255,0.045);
                --border: rgba(255,255,255,0.10);
                --border2: rgba(255,255,255,0.08);
                --text: rgba(255,255,255,0.92);
                --muted: rgba(255,255,255,0.72);
                --link: rgba(140, 180, 255, 0.95);
            }

            * { box-sizing: border-box; }

            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
                margin: 0;
                padding: 12px;
                background: var(--bg);
                color: var(--text);
                line-height: 1.35;
            }

            .bg {
                position: fixed;
                inset: 0;
                z-index: -1;
                pointer-events: none;
            }
            .bg .g1 {
                position: absolute;
                inset: 0;
                background: linear-gradient(to bottom, rgba(99,102,241,0.10), transparent, rgba(217,70,239,0.10));
            }
            .bg .blob1 {
                position: absolute;
                top: -80px;
                left: 50%;
                width: 380px;
                height: 380px;
                transform: translateX(-50%);
                border-radius: 999px;
                background: rgba(99,102,241,0.20);
                filter: blur(55px);
            }
            .bg .blob2 {
                position: absolute;
                bottom: -40px;
                right: -20px;
                width: 320px;
                height: 320px;
                border-radius: 999px;
                background: rgba(217,70,239,0.16);
                filter: blur(55px);
            }

            .container {
                max-width: 1100px;
                margin: 0 auto;
                background: var(--card);
                border-radius: 16px;
                overflow: hidden;
                border: 1px solid var(--border);
                backdrop-filter: blur(14px);
            }

            .header {
                background: rgba(255,255,255,0.04);
                border-bottom: 1px solid var(--border2);
                padding: 10px 12px;
            }
            .header-row {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 10px;
                flex-wrap: wrap;
            }
            .header-title {
                font-size: 15px;
                font-weight: 800;
                letter-spacing: 0.2px;
                margin: 0;
                white-space: nowrap;
            }
            .header-meta {
                display: flex;
                align-items: center;
                gap: 6px;
                flex-wrap: wrap;
            }

            .pill {
                background: rgba(0,0,0,0.25);
                border: 1px solid rgba(255,255,255,0.12);
                color: var(--muted);
                padding: 4px 8px;
                border-radius: 999px;
                font-size: 12px;
                font-weight: 700;
                white-space: nowrap;
            }
            .pill.strong { color: rgba(255,255,255,0.92); }

            .save-buttons {
                display: flex;
                gap: 6px;
            }
            .save-btn {
                background: rgba(255,255,255,0.08);
                border: 1px solid rgba(255,255,255,0.12);
                color: rgba(255,255,255,0.92);
                padding: 6px 10px;
                border-radius: 10px;
                cursor: pointer;
                font-size: 12px;
                font-weight: 700;
                transition: all 0.15s ease;
                white-space: nowrap;
            }
            .save-btn:hover { background: rgba(255,255,255,0.12); }
            .save-btn:active { transform: translateY(1px); }
            .save-btn:disabled { opacity: 0.6; cursor: not-allowed; }

            .content {
                padding: 10px 12px 14px 12px;
            }

            .word-group {
                margin: 10px 0;
                border-radius: 14px;
                overflow: hidden;
                background: var(--card2);
                border: 1px solid var(--border2);
            }

            .word-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 10px;
                padding: 8px 10px;
                border-bottom: 1px solid rgba(255,255,255,0.08);
            }

            .word-name {
                font-size: 13px;
                font-weight: 850;
                color: rgba(255,255,255,0.92);
                letter-spacing: 0.2px;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .word-meta {
                display: flex;
                align-items: center;
                gap: 6px;
                flex-wrap: wrap;
                justify-content: flex-end;
            }

            .badge {
                display: inline-flex;
                align-items: center;
                background: rgba(0,0,0,0.25);
                border: 1px solid rgba(255,255,255,0.12);
                color: rgba(255,255,255,0.78);
                padding: 2px 7px;
                border-radius: 999px;
                font-size: 11px;
                font-weight: 750;
                white-space: nowrap;
            }

            .badge.hot { background: rgba(220,38,38,0.18); border-color: rgba(220,38,38,0.45); color: rgba(255,255,255,0.92); }
            .badge.warm { background: rgba(234,88,12,0.18); border-color: rgba(234,88,12,0.45); color: rgba(255,255,255,0.92); }
            .badge.rank.top { background: rgba(220,38,38,0.30); border-color: rgba(220,38,38,0.65); color: #fff; }
            .badge.rank.high { background: rgba(234,88,12,0.26); border-color: rgba(234,88,12,0.6); color: #fff; }
            .badge.count { background: rgba(16,185,129,0.12); border-color: rgba(16,185,129,0.35); color: rgba(167,243,208,0.95); }
            .badge.new { background: rgba(251,191,36,0.95); border-color: rgba(251,191,36,0.95); color: rgba(17,24,39,0.95); font-weight: 900; letter-spacing: 0.2px; }
            .badge.muted { color: var(--muted); }

            .news-item {
                display: flex;
                gap: 8px;
                align-items: center;
                padding: 6px 10px;
                border-top: 1px solid rgba(255,255,255,0.08);
            }
            .news-item:first-child { border-top: none; }
            .news-item:hover { background: rgba(255,255,255,0.04); }

            .news-number {
                color: var(--muted);
                font-size: 12px;
                font-weight: 800;
                width: 22px;
                text-align: center;
                flex-shrink: 0;
            }

            .news-content {
                flex: 1;
                min-width: 0;
            }

            .news-line {
                display: flex;
                align-items: center;
                gap: 6px;
                min-width: 0;
            }

            .news-link {
                flex: 1;
                min-width: 240px;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                color: var(--link);
                text-decoration: none;
                font-size: 13px;
                font-weight: 700;
            }
            .news-link:hover { text-decoration: underline; }
            .news-link:visited { color: rgba(189, 151, 255, 0.95); }

            .new-section { margin-top: 12px; }
            .new-section-title { font-size: 13px; font-weight: 900; letter-spacing: 0.2px; margin: 0; color: rgba(255,255,255,0.92); }
            .new-source-title { color: var(--muted); font-size: 12px; font-weight: 800; margin: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
            .new-item {
                display: flex;
                align-items: center;
                gap: 6px;
                padding: 6px 10px;
                border-top: 1px solid rgba(255,255,255,0.08);
            }
            .new-item:first-child { border-top: none; }
            .new-item-number { width: 22px; text-align: center; color: var(--muted); font-weight: 900; font-size: 12px; flex-shrink: 0; }
            .new-item-content { flex: 1; min-width: 0; }

            .error-section {
                background: rgba(220,38,38,0.12);
                border: 1px solid rgba(220,38,38,0.35);
                border-radius: 14px;
                padding: 10px 12px;
                margin: 10px 0;
            }
            .error-title { color: rgba(255,255,255,0.92); font-size: 12px; font-weight: 900; margin: 0 0 6px 0; }
            .error-list { list-style: none; padding: 0; margin: 0; }
            .error-item { color: rgba(255,255,255,0.86); font-size: 12px; padding: 2px 0; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', monospace; }

            .footer {
                padding: 10px 12px;
                border-top: 1px solid rgba(255,255,255,0.08);
                color: var(--muted);
                font-size: 12px;
                text-align: center;
                background: rgba(255,255,255,0.04);
            }
            .footer a { color: var(--link); text-decoration: none; }
            .footer a:hover { text-decoration: underline; }

            @media (max-width: 640px) {
                body { padding: 10px; }
                .news-line { flex-wrap: wrap; }
                .news-link { min-width: 0; flex-basis: 100%; white-space: normal; }
                .save-buttons { width: 100%; justify-content: flex-end; }
            }

            @media print {
                body { background: #ffffff; color: #111827; }
                .bg { display: none; }
                .container { background: #ffffff; border-color: #e5e7eb; }
                .header, .footer { background: #ffffff; color: #111827; }
                .pill, .badge { background: #f3f4f6; border-color: #e5e7eb; color: #111827; }
                .news-link { color: #111827; }
            }
        </style>
    </head>
    <body>
        <div class="bg">
            <div class="g1"></div>
            <div class="blob1"></div>
            <div class="blob2"></div>
        </div>
        <div class="container">
            <div class="header">
                <div class="header-row">
                    <div class="header-title">热点新闻分析</div>
                    <div class="header-meta">
                        <span class="pill strong">"""

    html += html_escape(report_type_label)
    html += """</span>"""
    html += f'<span class="pill">总 {total_titles}</span>'
    html += f'<span class="pill">热点 {hot_news_count}</span>'
    html += f'<span class="pill">{html_escape(now_label)}</span>'

    html += """
                    </div>
                    <div class="save-buttons">
                        <button class="save-btn" onclick="saveAsImage()">保存为图片</button>
                        <button class="save-btn" onclick="saveAsMultipleImages()">分段保存</button>
                    </div>
                </div>
            </div>

            <div class="content">"""

    # 处理失败ID错误信息
    if report_data["failed_ids"]:
        html += """
                <div class="error-section">
                    <div class="error-title">⚠️ 请求失败的平台</div>
                    <ul class="error-list">"""
        for id_value in report_data["failed_ids"]:
            html += f'<li class="error-item">{html_escape(id_value)}</li>'
        html += """
                    </ul>
                </div>"""

    # 生成热点词汇统计部分的HTML
    stats_html = ""
    if report_data["stats"]:
        total_count = len(report_data["stats"])

        for i, stat in enumerate(report_data["stats"], 1):
            count = stat["count"]

            # 确定热度等级
            if count >= 10:
                count_class = "hot"
            elif count >= 5:
                count_class = "warm"
            else:
                count_class = ""

            escaped_word = html_escape(stat["word"])
            percentage = stat.get("percentage", 0)

            stats_html += f"""
                <div class="word-group">
                    <div class="word-header">
                        <div class="word-name">{escaped_word}</div>
                        <div class="word-meta">
                            <span class="badge {count_class}">{count}条</span>
                            <span class="badge muted">{percentage}%</span>
                            <span class="badge muted">{i}/{total_count}</span>
                        </div>
                    </div>"""

            # 处理每个词组下的新闻标题，给每条新闻标上序号
            for j, title_data in enumerate(stat["titles"], 1):
                is_new = title_data.get("is_new", False)
                new_class = "new" if is_new else ""

                stats_html += f"""
                    <div class="news-item {new_class}">
                        <div class="news-number">{j}</div>
                        <div class="news-content">
                            <div class="news-line">
                                <span class="badge">{html_escape(title_data["source_name"])}</span>"""

                # 处理排名显示
                ranks = title_data.get("ranks", [])
                if ranks:
                    min_rank = min(ranks)
                    max_rank = max(ranks)
                    rank_threshold = title_data.get("rank_threshold", 10)

                    # 确定排名等级
                    if min_rank <= 3:
                        rank_class = "top"
                    elif min_rank <= rank_threshold:
                        rank_class = "high"
                    else:
                        rank_class = ""

                    if min_rank == max_rank:
                        rank_text = str(min_rank)
                    else:
                        rank_text = f"{min_rank}-{max_rank}"

                    stats_html += f'<span class="badge rank {rank_class}">{rank_text}</span>'

                # 处理时间显示
                time_display = title_data.get("time_display", "")
                if time_display:
                    # 简化时间显示格式，将波浪线替换为~
                    simplified_time = (
                        time_display.replace(" ~ ", "~")
                        .replace("[", "")
                        .replace("]", "")
                    )
                    stats_html += (
                        f'<span class="badge muted">{html_escape(simplified_time)}</span>'
                    )

                # 处理出现次数
                count_info = title_data.get("count", 1)
                if count_info > 1:
                    stats_html += f'<span class="badge count">{count_info}次</span>'

                if is_new:
                    stats_html += '<span class="badge new">NEW</span>'

                # 处理标题和链接
                escaped_title = html_escape(title_data["title"])
                link_url = title_data.get("mobile_url") or title_data.get("url", "")

                if link_url:
                    escaped_url = html_escape(link_url)
                    stats_html += f'<a href="{escaped_url}" target="_blank" class="news-link">{escaped_title}</a>'
                else:
                    stats_html += f'<span class="news-link" style="color: rgba(255,255,255,0.92)">{escaped_title}</span>'

                stats_html += """
                            </div>
                        </div>
                    </div>"""

            stats_html += """
                </div>"""

    # 生成新增新闻区域的HTML
    new_titles_html = ""
    if report_data["new_titles"]:
        new_titles_html += f"""
                <div class="new-section">
                    <div class="word-group">
                        <div class="word-header">
                            <div class="new-section-title">本次新增热点</div>
                            <div class="word-meta">
                                <span class="badge warm">{report_data['total_new_count']}条</span>
                            </div>
                        </div>"""

        for source_data in report_data["new_titles"]:
            escaped_source = html_escape(source_data["source_name"])
            titles_count = len(source_data["titles"])

            new_titles_html += f"""
                        <div class="word-header" style="border-top: 1px solid rgba(255,255,255,0.08); border-bottom: none;">
                            <div class="new-source-title">{escaped_source}</div>
                            <div class="word-meta">
                                <span class="badge muted">{titles_count}条</span>
                            </div>
                        </div>"""

            # 为新增新闻也添加序号
            for idx, title_data in enumerate(source_data["titles"], 1):
                ranks = title_data.get("ranks", [])

                # 处理新增新闻的排名显示
                rank_class = ""
                if ranks:
                    min_rank = min(ranks)
                    if min_rank <= 3:
                        rank_class = "top"
                    elif min_rank <= title_data.get("rank_threshold", 10):
                        rank_class = "high"

                    if len(ranks) == 1:
                        rank_text = str(ranks[0])
                    else:
                        rank_text = f"{min(ranks)}-{max(ranks)}"
                else:
                    rank_text = "?"

                new_titles_html += f"""
                        <div class="new-item">
                            <div class="new-item-number">{idx}</div>
                            <div class="new-item-content">
                                <div class="news-line">"""

                new_titles_html += f'<span class="badge rank {rank_class}">{rank_text}</span>'

                # 处理新增新闻的链接
                escaped_title = html_escape(title_data["title"])
                link_url = title_data.get("mobile_url") or title_data.get("url", "")

                if link_url:
                    escaped_url = html_escape(link_url)
                    new_titles_html += f'<a href="{escaped_url}" target="_blank" class="news-link">{escaped_title}</a>'
                else:
                    new_titles_html += f'<span class="news-link" style="color: rgba(255,255,255,0.92)">{escaped_title}</span>'

                new_titles_html += """
                                </div>
                            </div>
                        </div>"""

        new_titles_html += """
                    </div>
                </div>"""

    # 根据配置决定内容顺序
    if reverse_content_order:
        # 新增热点在前，热点词汇统计在后
        html += new_titles_html + stats_html
    else:
        # 默认：热点词汇统计在前，新增热点在后
        html += stats_html + new_titles_html

    html += """
            </div>

            <div class="footer">
                TrendRadar ·
                <a href="https://github.com/sansan0/TrendRadar" target="_blank">
                    GitHub
                </a>"""

    if update_info:
        html += f"""
                <span style="margin-left: 8px; color: rgba(251,191,36,0.95); font-weight: 900;">
                    新版本 {update_info['remote_version']}（当前 {update_info['current_version']}）
                </span>"""

    html += """
            </div>
        </div>

        <script>
            async function saveAsImage() {
                const button = event.target;
                const originalText = button.textContent;

                try {
                    button.textContent = '生成中...';
                    button.disabled = true;
                    window.scrollTo(0, 0);

                    // 等待页面稳定
                    await new Promise(resolve => setTimeout(resolve, 200));

                    // 截图前隐藏按钮
                    const buttons = document.querySelector('.save-buttons');
                    buttons.style.visibility = 'hidden';

                    // 再次等待确保按钮完全隐藏
                    await new Promise(resolve => setTimeout(resolve, 100));

                    const container = document.querySelector('.container');

                    const canvas = await html2canvas(container, {
                        backgroundColor: '#0b1020',
                        scale: 1.5,
                        useCORS: true,
                        allowTaint: false,
                        imageTimeout: 10000,
                        removeContainer: false,
                        foreignObjectRendering: false,
                        logging: false,
                        width: container.offsetWidth,
                        height: container.offsetHeight,
                        x: 0,
                        y: 0,
                        scrollX: 0,
                        scrollY: 0,
                        windowWidth: window.innerWidth,
                        windowHeight: window.innerHeight
                    });

                    buttons.style.visibility = 'visible';

                    const link = document.createElement('a');
                    const now = new Date();
                    const filename = `TrendRadar_热点新闻分析_${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}_${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}.png`;

                    link.download = filename;
                    link.href = canvas.toDataURL('image/png', 1.0);

                    // 触发下载
                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);

                    button.textContent = '保存成功!';
                    setTimeout(() => {
                        button.textContent = originalText;
                        button.disabled = false;
                    }, 2000);

                } catch (error) {
                    const buttons = document.querySelector('.save-buttons');
                    buttons.style.visibility = 'visible';
                    button.textContent = '保存失败';
                    setTimeout(() => {
                        button.textContent = originalText;
                        button.disabled = false;
                    }, 2000);
                }
            }

            async function saveAsMultipleImages() {
                const button = event.target;
                const originalText = button.textContent;
                const container = document.querySelector('.container');
                const scale = 1.5;
                const maxHeight = 5000 / scale;

                try {
                    button.textContent = '分析中...';
                    button.disabled = true;

                    // 获取所有可能的分割元素
                    const newsItems = Array.from(container.querySelectorAll('.news-item'));
                    const wordGroups = Array.from(container.querySelectorAll('.word-group'));
                    const newSection = container.querySelector('.new-section');
                    const errorSection = container.querySelector('.error-section');
                    const header = container.querySelector('.header');
                    const footer = container.querySelector('.footer');

                    // 计算元素位置和高度
                    const containerRect = container.getBoundingClientRect();
                    const elements = [];

                    // 添加header作为必须包含的元素
                    elements.push({
                        type: 'header',
                        element: header,
                        top: 0,
                        bottom: header.offsetHeight,
                        height: header.offsetHeight
                    });

                    // 添加错误信息（如果存在）
                    if (errorSection) {
                        const rect = errorSection.getBoundingClientRect();
                        elements.push({
                            type: 'error',
                            element: errorSection,
                            top: rect.top - containerRect.top,
                            bottom: rect.bottom - containerRect.top,
                            height: rect.height
                        });
                    }

                    // 按word-group分组处理news-item
                    wordGroups.forEach(group => {
                        const groupRect = group.getBoundingClientRect();
                        const groupNewsItems = group.querySelectorAll('.news-item');

                        // 添加word-group的header部分
                        const wordHeader = group.querySelector('.word-header');
                        if (wordHeader) {
                            const headerRect = wordHeader.getBoundingClientRect();
                            elements.push({
                                type: 'word-header',
                                element: wordHeader,
                                parent: group,
                                top: groupRect.top - containerRect.top,
                                bottom: headerRect.bottom - containerRect.top,
                                height: headerRect.height
                            });
                        }

                        // 添加每个news-item
                        groupNewsItems.forEach(item => {
                            const rect = item.getBoundingClientRect();
                            elements.push({
                                type: 'news-item',
                                element: item,
                                parent: group,
                                top: rect.top - containerRect.top,
                                bottom: rect.bottom - containerRect.top,
                                height: rect.height
                            });
                        });
                    });

                    // 添加新增新闻部分
                    if (newSection) {
                        const rect = newSection.getBoundingClientRect();
                        elements.push({
                            type: 'new-section',
                            element: newSection,
                            top: rect.top - containerRect.top,
                            bottom: rect.bottom - containerRect.top,
                            height: rect.height
                        });
                    }

                    // 添加footer
                    const footerRect = footer.getBoundingClientRect();
                    elements.push({
                        type: 'footer',
                        element: footer,
                        top: footerRect.top - containerRect.top,
                        bottom: footerRect.bottom - containerRect.top,
                        height: footer.offsetHeight
                    });

                    // 计算分割点
                    const segments = [];
                    let currentSegment = { start: 0, end: 0, height: 0, includeHeader: true };
                    let headerHeight = header.offsetHeight;
                    currentSegment.height = headerHeight;

                    for (let i = 1; i < elements.length; i++) {
                        const element = elements[i];
                        const potentialHeight = element.bottom - currentSegment.start;

                        // 检查是否需要创建新分段
                        if (potentialHeight > maxHeight && currentSegment.height > headerHeight) {
                            // 在前一个元素结束处分割
                            currentSegment.end = elements[i - 1].bottom;
                            segments.push(currentSegment);

                            // 开始新分段
                            currentSegment = {
                                start: currentSegment.end,
                                end: 0,
                                height: element.bottom - currentSegment.end,
                                includeHeader: false
                            };
                        } else {
                            currentSegment.height = potentialHeight;
                            currentSegment.end = element.bottom;
                        }
                    }

                    // 添加最后一个分段
                    if (currentSegment.height > 0) {
                        currentSegment.end = container.offsetHeight;
                        segments.push(currentSegment);
                    }

                    button.textContent = `生成中 (0/${segments.length})...`;

                    // 隐藏保存按钮
                    const buttons = document.querySelector('.save-buttons');
                    buttons.style.visibility = 'hidden';

                    // 为每个分段生成图片
                    const images = [];
                    for (let i = 0; i < segments.length; i++) {
                        const segment = segments[i];
                        button.textContent = `生成中 (${i + 1}/${segments.length})...`;

                        // 创建临时容器用于截图
                        const tempContainer = document.createElement('div');
                        tempContainer.style.cssText = `
                            position: absolute;
                            left: -9999px;
                            top: 0;
                            width: ${container.offsetWidth}px;
                            background: white;
                        `;
                        tempContainer.className = 'container';

                        // 克隆容器内容
                        const clonedContainer = container.cloneNode(true);

                        // 移除克隆内容中的保存按钮
                        const clonedButtons = clonedContainer.querySelector('.save-buttons');
                        if (clonedButtons) {
                            clonedButtons.style.display = 'none';
                        }

                        tempContainer.appendChild(clonedContainer);
                        document.body.appendChild(tempContainer);

                        // 等待DOM更新
                        await new Promise(resolve => setTimeout(resolve, 100));

                        // 使用html2canvas截取特定区域
                        const canvas = await html2canvas(clonedContainer, {
                            backgroundColor: '#0b1020',
                            scale: scale,
                            useCORS: true,
                            allowTaint: false,
                            imageTimeout: 10000,
                            logging: false,
                            width: container.offsetWidth,
                            height: segment.end - segment.start,
                            x: 0,
                            y: segment.start,
                            windowWidth: window.innerWidth,
                            windowHeight: window.innerHeight
                        });

                        images.push(canvas.toDataURL('image/png', 1.0));

                        // 清理临时容器
                        document.body.removeChild(tempContainer);
                    }

                    // 恢复按钮显示
                    buttons.style.visibility = 'visible';

                    // 下载所有图片
                    const now = new Date();
                    const baseFilename = `TrendRadar_热点新闻分析_${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}_${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}`;

                    for (let i = 0; i < images.length; i++) {
                        const link = document.createElement('a');
                        link.download = `${baseFilename}_part${i + 1}.png`;
                        link.href = images[i];
                        document.body.appendChild(link);
                        link.click();
                        document.body.removeChild(link);

                        // 延迟一下避免浏览器阻止多个下载
                        await new Promise(resolve => setTimeout(resolve, 100));
                    }

                    button.textContent = `已保存 ${segments.length} 张图片!`;
                    setTimeout(() => {
                        button.textContent = originalText;
                        button.disabled = false;
                    }, 2000);

                } catch (error) {
                    console.error('分段保存失败:', error);
                    const buttons = document.querySelector('.save-buttons');
                    buttons.style.visibility = 'visible';
                    button.textContent = '保存失败';
                    setTimeout(() => {
                        button.textContent = originalText;
                        button.disabled = false;
                    }, 2000);
                }
            }

            document.addEventListener('DOMContentLoaded', function() {
                window.scrollTo(0, 0);
            });
        </script>
    </body>
    </html>
    """

    return html
