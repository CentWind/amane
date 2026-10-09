import re
from collections.abc import Mapping
from urllib.parse import quote, urljoin

from parsel import Selector

from ...enums import ActorGender, SiteName
from ..base import Crawler, CrawlerProfile
from ..models import FetchOptions, FilmActor, MediaMetadata, SearchQuery
from ..parsing import extract_all_texts, extract_text, is_same_number, parse_western_number


def expand_search_terms(number: str, aliases: Mapping[str, str]) -> list[str]:
    """番号 → 依次尝试的检索词: 站点别名替换后的番号, 原番号, 以及欧美日期号的另一种年份写法.

    素人番号在 DMM 上带数字头 (``300MIUM-123``), 站内只有 ``MIUM-123``, 因此把配置的
    前缀→前缀替换结果作为该番号的首个检索词. 配置别名即声明本站不认原形态, 先试别名可省掉
    必然落空的那次请求; 别名未命中时仍回退原番号. 检索词同时是命中判据, 二者必须成对使用:
    用替换后的番号搜到条目, 却与替换前的番号比对, 会判定未命中.

    前缀匹配不区分大小写, 同一番号至多替换一次; 空前缀与非匹配前缀不产出检索词, 替换结果为空串
    或与既有检索词相同时不追加.
    """
    terms: list[str] = []
    for base in _base_search_terms(number):
        alias = _alias_number(base, aliases)
        if alias and alias not in terms:
            terms.append(alias)
        if base not in terms:
            terms.append(base)
    return terms


def _base_search_terms(number: str) -> list[str]:
    """原番号; 欧美日期号在站内两套年份写法并存, 另一种写法作为额外检索词."""
    terms = [number]
    western = parse_western_number(number)
    if western is not None and western.alternate != number:
        terms.append(western.alternate)
    return terms


def _alias_number(number: str, aliases: Mapping[str, str]) -> str | None:
    """命中别名前缀时把番号开头的该前缀替换成对应检索词前缀; 无命中返回 ``None``.

    多个前缀都能命中时取最长者: 短前缀 (``300``) 会截断长前缀 (``300MIUM``) 的替换范围.
    """
    folded = number.casefold()
    matched: str | None = None
    for prefix in aliases:
        if not prefix or not folded.startswith(prefix.casefold()):
            continue
        if matched is None or len(prefix) > len(matched):
            matched = prefix
    if matched is None:
        return None
    return aliases[matched] + number[len(matched) :]


def _parse_actors(html: Selector) -> list[FilmActor]:
    """演員栏: ``a.actor-female`` 为女优; 同栏无该 class 的 ``a`` 为男优."""
    container = html.xpath('//strong[contains(text(),"演員")]/following-sibling::span[contains(@class,"value")][1]')
    if not container:
        return []
    actors: list[FilmActor] = []
    for node in container[0].xpath("./a"):
        name = (node.xpath("string()").get() or "").strip()
        if not name:
            continue
        classes = (node.root.get("class") or "").split()
        gender = ActorGender.FEMALE if "actor-female" in classes else ActorGender.MALE
        actors.append(FilmActor(name=name, gender=gender))
    return actors


class JavDBCrawler(Crawler):
    @classmethod
    def profile(cls) -> CrawlerProfile:
        return CrawlerProfile(name=SiteName.JAVDB, base_url="https://javdb.com")

    async def _search(self, query: SearchQuery, options: FetchOptions | None = None) -> str | None:
        """结果番号取自条目声明的 ``div.video-title/strong``, 与本次检索词不同者视为未命中.

        检索词由 ``expand_search_terms`` 展开 (站点别名与欧美日期号的另一种年份写法), 命中判据
        始终是实际用于检索的那个词.
        """
        aliases = self.config.number_aliases if self.config is not None else {}
        for term in expand_search_terms(query.number, aliases):
            url = await self._search_term(term)
            if url is not None:
                return url
        return None

    async def _search_term(self, term: str) -> str | None:
        text = await self.client.get_html(f"{self.base_url}/search?q={quote(term)}&locale=zh", cookies=self.cookies)
        html = Selector(text=text)

        for item in html.xpath("//a[@class='box']"):
            href = extract_text(item, "@href")
            found = extract_text(item, "div[@class='video-title']/strong/text()")
            if href and found and is_same_number(found, term):
                return urljoin(self.base_url, href)
        return None

    async def _scrape(self, url: str, options: FetchOptions | None = None) -> MediaMetadata | None:
        text = await self.client.get_html(url, cookies=self.cookies)
        html = Selector(text=text)

        number = extract_text(html, '//a[@class="button is-white copy-to-clipboard"]/@data-clipboard-text')
        if not number:
            return None

        title = extract_text(html, 'string(//h2[@class="title is-4"]/strong[@class="current-title"])')

        studio = extract_text(
            html,
            '//strong[contains(text(),"片商:")]/following-sibling::span/a/text()',
            '//strong[contains(text(),"片商:")]/../span/a/text()',
        )
        publisher = extract_text(
            html,
            '//strong[contains(text(),"發行:")]/following-sibling::span/a/text()',
            '//strong[contains(text(),"發行:")]/../span/a/text()',
        )
        runtime_str = extract_text(
            html,
            '//strong[contains(text(),"時長")]/following-sibling::span/text()',
            '//strong[contains(text(),"時長")]/../span/text()',
        )
        runtime = self._parse_runtime(runtime_str)

        release = extract_text(
            html,
            '//strong[contains(text(),"日期:")]/following-sibling::span/text()',
            '//strong[contains(text(),"日期:")]/../span/text()',
        )
        series = extract_text(
            html,
            '//strong[contains(text(),"系列:")]/following-sibling::span/a/text()',
            '//strong[contains(text(),"系列:")]/../span/a/text()',
        )
        directors = extract_all_texts(
            html,
            '//strong[contains(text(),"導演:")]/following-sibling::span/a/text()',
            '//strong[contains(text(),"導演:")]/../span/a/text()',
        )
        tags = extract_all_texts(
            html,
            '//strong[contains(text(),"類別:")]/following-sibling::span/a/text()',
            '//strong[contains(text(),"類別:")]/../span/a/text()',
        )
        tags = [t.strip() for t in tags if t.strip()]

        actors = _parse_actors(html)

        thumb_url = extract_text(html, "//img[@class='video-cover']/@src")

        score_text = extract_text(html, "//span[@class='score-stars']/following-sibling::text()[1]")
        score = self._parse_score(score_text)

        extrafanart = extract_all_texts(html, "//div[@class='tile-images preview-images']/a[@class='tile-item']/@href")
        trailer_url = extract_text(html, "//video[@id='preview-video']/source/@src")

        return MediaMetadata(
            number=number,
            title=title,
            actors=actors,
            studio=studio or None,
            publisher=publisher or None,
            release=release or None,
            runtime=runtime,
            tags=tags,
            series=series or None,
            directors=directors,
            thumb_urls=[thumb_url] if thumb_url else [],
            score=score,
            extrafanart=extrafanart,
            trailer_urls=[trailer_url] if trailer_url else [],
            source_url=url,
            external_id=url,
        )

    @staticmethod
    def _parse_runtime(text: str) -> int | None:
        if not text:
            return None
        match = re.search(r"(\d+)", text)
        return int(match.group(1)) if match else None

    @staticmethod
    def _parse_score(text: str) -> float | None:
        if not text:
            return None
        match = re.search(r"(\d+\.?\d*)", text)
        return float(match.group(1)) if match else None
