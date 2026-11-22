"""그림 도구 — HwpxDoc 믹스인(spec_그림 ② §2~§6). 그림 파일 바꾸기(선명하게) · 개체 캡션 붙이기(표 · 그림) · 가운데 · 두 그림 한 줄에.

부르는 쪽(`app/pic_tools_api.py`)이 `server._edit` 트랜잭션 안에서 부른다 — 여기서는 문서만 바꾸고 실행 취소 · 검사는 트랜잭션이 맡는다.
그림을 읽는 순수 로직(선명하게 · LLM 계약)은 `app/pic_tools.py`."""
import mimetypes
from collections import Counter

from lxml import etree

from app import hwpx_layout
from app.hwpx_format import HC, HP, _p

P, RUN, T, TBL, PIC, CAPTION, SUBLIST, LINESEG = map(_p, ["p", "run", "t", "tbl", "pic", "caption", "subList", "linesegarray"])
NS = {"hp": HP, "hc": HC}
SUB_ATTRS = {"id": "", "textDirection": "HORIZONTAL", "lineWrap": "BREAK", "vertAlign": "TOP", "linkListIDRef": "0", "linkListNextIDRef": "0",
             "textWidth": "0", "textHeight": "0", "hasTextRef": "0", "hasNumRef": "0"}   # 한글이 쓰는 캡션 subList 의 속성(references/HWPX_포맷.md 「캡션」)
CAP_GAP = "850"          # 캡션과 개체 사이 3mm(HWPUNIT) — 문서에 본보기 캡션이 없을 때
ROW_GAP_MM = 3.0         # 한 줄에 놓은 두 그림 사이
_hu = hwpx_layout.hu


class PicMixin:
    # ---------------------------------------------------------------- 읽기
    def _pic(self, pid):
        el = self._ids.get(pid)
        if el is None or el.tag != PIC or not self._attached(el):
            raise ValueError("그 그림이 지금 문서에 없습니다")
        return el

    def pic_info(self, pid) -> dict:
        """그림 하나 {id, media(BinData 이름) | None, widthMm, heightMm, inline(글자처럼 취급), host(그림을 품은 문단 id), align(그 문단의 정렬),
        cell(칸 안인가), caption(개체 캡션이 있나)}."""
        pic = self._pic(pid)
        img, sz, pos = pic.find(f"{{{HC}}}img"), pic.find(_p("sz")), pic.find(_p("pos"))
        href = self._href(img.get("binaryItemIDRef")) if img is not None else None
        host = self._host(pic)
        mm = lambda v: round(_hu(v) * 25.4 / 7200, 1) if v else None  # noqa: E731
        return {"id": pid, "media": href if href and self._has(href) else None,
                "widthMm": mm(sz.get("width")) if sz is not None else None, "heightMm": mm(sz.get("height")) if sz is not None else None,
                "inline": pos is not None and pos.get("treatAsChar") == "1",
                "host": self._id(host), "align": (self._pic_para_look(host) or {}).get("align"),
                "cell": next(host.iterancestors(_p("tc")), None) is not None, "caption": pic.find(CAPTION) is not None}

    def _pic_para_look(self, p):
        try:
            return self._summary(p.get("paraPrIDRef"), self._char_id(p))
        except Exception:  # noqa: BLE001 — 모양 요약을 못 읽어도 정보는 낸다
            return None

    # ---------------------------------------------------------------- 그림 파일 바꾸기(선명하게 — ② §4)
    def pic_replace(self, pid, data: bytes, ext: str, wpx: int, hpx: int) -> str:
        """그림이 가리키는 그림 파일을 data 로(새 BinData — 같은 파일을 쓰는 다른 그림은 그대로) -> 새 manifest item id.
        표시 크기(hp:sz · curSz)는 그대로 두고 원본 크기 · 자르기 · 그림 상자 · 배율은 새 화소에 맞춰 같은 비율로 바꾼다."""
        pic = self._pic(pid)
        img = pic.find(f"{{{HC}}}img")
        if img is None:
            raise ValueError("그림 파일을 가리키지 않는 그림입니다")
        org = pic.find(_p("orgSz"))
        ow, oh = (_hu(org.get("width")), _hu(org.get("height"))) if org is not None else (0, 0)
        nw, nh = wpx * 75, hpx * 75           # 96dpi 화소 × 75 = HWPUNIT(references/HWPX_포맷.md 「그림」)
        fx, fy = (nw / ow if ow else 1.0), (nh / oh if oh else 1.0)
        iid = self._add_bin(data, ext, mimetypes.guess_type("x." + ext)[0] or f"image/{ext}")
        img.set("binaryItemIDRef", iid)
        if org is not None:
            org.set("width", str(nw))
            org.set("height", str(nh))
        for i in range(4):
            pt = pic.find(f"hp:imgRect/hc:pt{i}", NS)
            if pt is not None:
                pt.set("x", str(round(_hu(pt.get("x")) * fx)))
                pt.set("y", str(round(_hu(pt.get("y")) * fy)))
        clip = pic.find(_p("imgClip"))
        if clip is not None:
            for a, f in (("left", fx), ("right", fx), ("top", fy), ("bottom", fy)):
                clip.set(a, str(round(_hu(clip.get(a)) * f)))
        dim = pic.find(_p("imgDim"))
        if dim is not None:
            dim.set("dimwidth", str(nw))
            dim.set("dimheight", str(nh))
        sca = pic.find("hp:renderingInfo/hc:scaMatrix", NS)
        if sca is not None:
            for a, f in (("e1", fx), ("e5", fy)):
                sca.set(a, f"{float(sca.get(a, '1')) / f:.6f}")
        self._touch(pic)
        return iid

    # ---------------------------------------------------------------- 개체 캡션(② §2 · §3)
    def _caption_like(self, tag):
        """같은 대상(tag = TBL | PIC)의 개체 캡션 가운데 가장 많이 쓴 (첫 글 문단의 문단 모양 · 스타일 · 글자 모양 · 캡션 속성) -> (본보기 문단, 캡션 속성) | (None, None)."""
        seen, sample = Counter(), {}
        for sec in self._sections:
            for cap in sec.iter(CAPTION):
                if cap.getparent() is None or cap.getparent().tag != tag:
                    continue
                p = next((x for s in cap.iterchildren(SUBLIST) for x in s.iterchildren(P) if self._text(x).strip()), None)
                if p is None:
                    continue
                key = (p.get("paraPrIDRef"), p.get("styleIDRef"), self._char_id(p), cap.get("side"))
                seen[key] += 1
                sample.setdefault(key, (p, dict(cap.attrib)))
        if not seen:
            return None, None
        return sample[seen.most_common(1)[0][0]]

    def _text_caption_like(self, kind_blocks):
        """글 캡션 문단의 본보기(웹 블록 id 목록 — 부르는 쪽이 pic_tools.captions 로 고른 것) 가운데 가장 많이 쓴 모양의 문단 | None."""
        seen, sample = Counter(), {}
        for bid in kind_blocks or ():
            p = self._ids.get(bid)
            if p is None or p.tag != P or not self._attached(p):
                continue
            key = (p.get("paraPrIDRef"), p.get("styleIDRef"), self._char_id(p))
            seen[key] += 1
            sample.setdefault(key, p)
        return sample[seen.most_common(1)[0][0]] if seen else None

    def obj_caption_set(self, oid, lines, *, side=None, like_text=None) -> list[str]:
        """개체(표 | 그림 — 웹 블록 id) oid 에 개체 캡션을 붙인다(있으면 그 글을 바꾼다) -> 캡션 문단 id 목록.
        lines = 캡션 문단의 글(첫 줄 = 제목). 모양: 같은 대상의 개체 캡션 가운데 가장 많이 쓴 것 → like_text(글 캡션 문단 id 목록)의 가장 많이 쓴 것 → 개체를 품은 문단(② §3 「캡션의 모양」).
        side 기본 = 표 TOP · 그림 BOTTOM(실문서의 거의 전부 — references/HWPX_포맷.md 「캡션」)."""
        obj = self._ids.get(oid)
        if obj is None or obj.tag not in (TBL, PIC) or not self._attached(obj):
            raise ValueError("캡션을 붙일 표·그림이 지금 문서에 없습니다")
        lines = [" ".join(str(x).split()) for x in lines or () if str(x).strip()]
        if not lines:
            raise ValueError("캡션 글이 비었습니다")
        like, attrs = self._caption_like(obj.tag)
        if like is None:
            like = self._text_caption_like(like_text)
        if like is None:
            like = self._host(obj)
        side = side or (attrs or {}).get("side") or ("TOP" if obj.tag == TBL else "BOTTOM")
        sz = obj.find(_p("sz"))
        width = sz.get("width") if sz is not None else "0"
        cap = obj.find(CAPTION)
        if cap is not None:
            obj.remove(cap)
        cap = obj.makeelement(CAPTION, {"side": side, "fullSz": (attrs or {}).get("fullSz", "0"), "width": (attrs or {}).get("width", "8504"),
                                        "gap": (attrs or {}).get("gap", CAP_GAP), "lastWidth": width})
        sub = etree.SubElement(cap, SUBLIST, SUB_ATTRS)
        out = []
        for text in lines:
            p = etree.SubElement(sub, P, {"id": "0", "paraPrIDRef": like.get("paraPrIDRef", "0"), "styleIDRef": like.get("styleIDRef", "0"),
                                          "pageBreak": "0", "columnBreak": "0", "merged": "0"})
            run = etree.SubElement(p, RUN, {"charPrIDRef": self._char_id(like)})
            self._write_t(etree.SubElement(run, T), text)
            out.append(self._id(p))
        anchor = obj.find(_p("outMargin"))   # 자리: outMargin 바로 뒤(표 · 그림 모두 — references/HWPX_포맷.md 「캡션」)
        if anchor is None:
            anchor = obj.find(_p("pos"))
        if anchor is not None:
            anchor.addnext(cap)
        else:
            obj.append(cap)
        host = self._host(obj)
        for ls in host.findall(LINESEG):   # 줄 배치 캐시 — 개체의 높이가 캡션만큼 바뀌었다(한글이 다시 잰다)
            host.remove(ls)
        self._touch(obj)
        return out

    # ---------------------------------------------------------------- 가운데(② §5)
    def pic_center(self, pids) -> list[str]:
        """그림들을 가운데로 -> 바뀐 그림 id. 글자처럼 취급 = 품은 문단의 정렬 · 떠 있는 그림 = 가로 자리 「단 가운데」."""
        done = []
        for pid in dict.fromkeys(pids):
            pic = self._pic(pid)
            pos = pic.find(_p("pos"))
            if pos is not None and pos.get("treatAsChar") != "1":
                want = {"horzRelTo": "COLUMN", "horzAlign": "CENTER", "horzOffset": "0"}
                if any(pos.get(k) != v for k, v in want.items()):
                    pos.attrib.update(want)
                    self._touch(pic)
                    done.append(pid)
                continue
            host = self._host(pic)
            if (self._pic_para_look(host) or {}).get("align") == "center":
                continue
            if self.format_para([self._id(host)], {"align": "center"}):
                done.append(pid)
        return done

    # ---------------------------------------------------------------- 한 줄에(② §6)
    def _order(self, a, b):
        """문서 차례로 (앞, 뒤)."""
        root = a.getroottree().getroot()
        if root is not b.getroottree().getroot():
            sa = next(i for i, s in enumerate(self._sections) if s is root)
            sb = next(i for i, s in enumerate(self._sections) if s is b.getroottree().getroot())
            return (a, b) if sa <= sb else (b, a)
        for e in root.iter(PIC):
            if e is a:
                return a, b
            if e is b:
                return b, a
        return a, b

    @staticmethod
    def _scale_pic(pic, f):
        for tag in ("sz", "curSz"):
            if (e := pic.find(_p(tag))) is not None and _hu(e.get("width")):
                e.set("width", str(round(_hu(e.get("width")) * f)))
                e.set("height", str(round(_hu(e.get("height")) * f)))
        sz = pic.find(_p("sz"))
        if (rot := pic.find(_p("rotationInfo"))) is not None and sz is not None:
            rot.set("centerX", str(_hu(sz.get("width")) // 2))
            rot.set("centerY", str(_hu(sz.get("height")) // 2))
        sca = pic.find("hp:renderingInfo/hc:scaMatrix", NS)
        if sca is not None:
            for a in ("e1", "e5"):
                sca.set(a, f"{float(sca.get(a, '1')) * f:.6f}")
        cap = pic.find(CAPTION)
        if cap is not None and sz is not None:
            cap.set("lastWidth", sz.get("width"))

    def pic_row(self, pid_a, pid_b) -> dict:
        """두 그림을 문서 차례가 앞선 그림의 문단에 한 줄로 -> {"first", "second", "host": 앞 그림의 문단 id, "removed": [지운 문단 id], "scaled": 줄인 비율 | None}.
        같은 그릇(본문끼리 · 같은 칸)이 아니면 ValueError. 뒤 그림이 홀로 있던 글 없는 문단은 지운다."""
        if pid_a == pid_b:
            raise ValueError("서로 다른 그림 둘을 고르세요")
        a, b = self._order(self._pic(pid_a), self._pic(pid_b))
        ha, hb = self._host(a), self._host(b)
        box = lambda h: next(h.iterancestors(SUBLIST), None)  # noqa: E731 — 칸·캡션 안이면 그 subList, 본문이면 None
        if box(ha) is not box(hb) or (box(ha) is None and ha.getparent() is not hb.getparent()):
            raise ValueError("두 그림이 같은 곳(본문끼리 · 같은 칸)에 있어야 한 줄에 놓을 수 있습니다")
        for pic in (a, b):
            pos = pic.find(_p("pos"))
            if pos is not None and pos.get("treatAsChar") != "1":
                pos.attrib.update({"treatAsChar": "1", "vertOffset": "0", "horzOffset": "0"})
        room = round(self._body_width_mm(ha) * 7200 / 25.4) - 140
        gap = round(ROW_GAP_MM * 7200 / 25.4)
        wa, wb = (_hu(p.find(_p("sz")).get("width")) if p.find(_p("sz")) is not None else 0 for p in (a, b))
        scaled = None
        if wa + wb + gap > room > gap and wa + wb:
            scaled = (room - gap) / (wa + wb)
            for pic in (a, b):
                self._scale_pic(pic, scaled)
        old_run = b.getparent()
        old_run.remove(b)
        sep = a.makeelement(T, {})
        sep.text = " "              # 두 그림 사이 — 한글은 글자처럼 취급한 개체를 글자처럼 늘어놓는다(빈칸 하나 · 폭 셈의 사이 3mm 는 그 몫과 여유)
        a.addnext(sep)
        sep.addnext(b)
        removed = []
        if hb is not ha:
            if len(old_run) == 0 or all(c.tag == T and not (c.text or "").strip() and len(c) == 0 for c in old_run):
                if not [c for r in hb.iterchildren(RUN) for c in r if c.tag != T] and not self._text(hb).strip() and hb.find(f".//{{{HP}}}secPr") is None:
                    removed = [self._rev[e] for e in hb.iter() if e in self._rev]
                    parent = hb.getparent()
                    parent.remove(hb)
                    self._touch(parent)
            if hb.getparent() is not None:
                for ls in hb.findall(LINESEG):
                    hb.remove(ls)
                self._touch(hb)
        for ls in ha.findall(LINESEG):
            ha.remove(ls)
        self._touch(ha)
        hid = self._id(ha)
        if (self._pic_para_look(ha) or {}).get("align") != "center":
            self.format_para([hid], {"align": "center"})
        return {"first": self._id(a), "second": self._id(b), "host": hid, "removed": removed, "scaled": round(scaled, 3) if scaled else None}
