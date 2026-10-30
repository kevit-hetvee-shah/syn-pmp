"""Low-level python-pptx slide duplication — the mechanism that makes real
pagination possible (vs. just growing one table indefinitely, which breaks
down visually once a customer has many products/segments).

python-pptx has no built-in "duplicate slide" API. A naive approach (just
deep-copying the slide's shape tree) silently breaks any chart on that
slide: `Chart.replace_data()` writes into the chart's own embedded-xlsx
part, and if a clone's chart XML still points at the *same* embedded-xlsx
relationship as the original, filling in the clone's chart data overwrites
the original's data too (they'd share one physical part). Fixed here by
giving every cloned chart its own independent chart part AND its own
independent embedded-xlsx part — verified 2026-10-31 by round-tripping a
save/reload and confirming two cloned charts on the same deck hold
genuinely different category/value data.
"""

from __future__ import annotations

import copy

from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.oxml.ns import qn
from pptx.parts.chart import ChartPart
from pptx.parts.embeddedpackage import EmbeddedXlsxPart

_R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_RID_ATTRS = (f"{{{_R_NS}}}id", f"{{{_R_NS}}}embed", f"{{{_R_NS}}}link")


def _remap_rids(root_el, rid_map: dict[str, str]) -> None:
    for el in root_el.iter():
        for attr in _RID_ATTRS:
            old = el.get(attr)
            if old in rid_map:
                el.set(attr, rid_map[old])


def _clone_chart_part(package, source_chart_part: ChartPart) -> ChartPart:
    new_partname = package.next_partname(ChartPart.partname_template)
    new_element = copy.deepcopy(source_chart_part._element)
    new_chart_part = ChartPart(new_partname, source_chart_part.content_type, package, new_element)

    chart_rid_map: dict[str, str] = {}
    for rel in list(source_chart_part.rels.values()):
        target = rel.target_part
        # The embedded xlsx (the "Edit Data in Excel" source) must be its
        # own independent part per clone — everything else on a chart part
        # can safely be shared.
        new_target = (
            EmbeddedXlsxPart.new(target.blob, package) if isinstance(target, EmbeddedXlsxPart) else target
        )
        chart_rid_map[rel.rId] = new_chart_part.relate_to(new_target, rel.reltype)

    _remap_rids(new_element, chart_rid_map)
    return new_chart_part


def clone_slide(prs, source_slide):
    """Append a full duplicate of `source_slide` to `prs` and return the new
    Slide. Always appends at the end (python-pptx's own `add_slide`
    behavior) — use `reorder_slides` afterwards to move it to where it
    belongs in the deck.
    """
    layout = source_slide.slide_layout
    new_slide = prs.slides.add_slide(layout)

    new_cSld = new_slide.part._element.find(qn("p:cSld"))
    old_spTree = new_cSld.find(qn("p:spTree"))
    new_spTree = copy.deepcopy(source_slide.part._element.find(qn("p:cSld")).find(qn("p:spTree")))
    new_cSld.replace(old_spTree, new_spTree)
    # `Slide.shapes` is a lazyproperty, already evaluated (and cached) by
    # add_slide()'s internal clone_layout_placeholders() call, *before* the
    # spTree swap above — without clearing it, every shape lookup on this
    # slide would keep returning the stale pre-swap placeholder shapes.
    new_slide.__dict__.pop("shapes", None)

    rid_map: dict[str, str] = {}
    for rel in list(source_slide.part.rels.values()):
        if rel.reltype == RT.SLIDE_LAYOUT or "notesSlide" in rel.reltype:
            continue  # layout is already set by add_slide(); clones don't need speaker notes
        if rel.reltype == RT.CHART:
            new_chart_part = _clone_chart_part(prs.part.package, rel.target_part)
            rid_map[rel.rId] = new_slide.part.relate_to(new_chart_part, RT.CHART)
        else:
            # Safe to share (e.g. a static background image) — only chart
            # data needs independence.
            rid_map[rel.rId] = new_slide.part.relate_to(rel.target_part, rel.reltype)

    _remap_rids(new_spTree, rid_map)
    return new_slide


def reorder_slides(prs, ordered_slides: list) -> None:
    """Rearrange the presentation's slide sequence to match `ordered_slides`
    (every slide currently in `prs.slides`, in the desired final order; pass
    the same Slide objects you already have — `Slide` isn't hashable, so
    this keys internally by Python object identity).
    Needed because `clone_slide` always appends at the end.
    """
    sldIdLst = prs.slides._sldIdLst
    sldId_by_identity = {id(slide): sldId for slide, sldId in zip(prs.slides, sldIdLst)}
    for sldId in list(sldIdLst):
        sldIdLst.remove(sldId)
    for slide in ordered_slides:
        sldIdLst.append(sldId_by_identity[id(slide)])
