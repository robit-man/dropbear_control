#!/usr/bin/env python3
"""Generate a local-only independent CAD review workbench from exact evidence."""

from __future__ import annotations

import argparse
import html
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import manage_cad_review_decisions as decisions


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "generated" / "myactuator" / "cad" / "review_workbenches"


class WorkbenchError(ValueError):
    pass


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True)


def render_html(template: dict[str, Any], context: dict[str, Any]) -> str:
    source = context["source"]
    packet = context["packet"]
    report = context["report"]
    packet_path = (
        ROOT
        / "generated/myactuator/cad/review_packets"
        / source["variant_id"]
        / "packet.json"
    )
    packet_local = json.loads(packet_path.read_text(encoding="utf-8"))
    embedded = canonical_json(
        {
            "template": template,
            "members": packet_local["members"],
            "candidate_articulation": report["articulation"],
        }
    ).replace("</", "<\\/")
    identity = html.escape(
        canonical_json(
            {
                "decision_id": template["decision_id"],
                "configuration_id": template["configuration_id"],
                "variant_id": template["variant_id"],
                "source_hashes": template["source_hashes"],
            }
        )
    )
    rows = []
    output_candidates = set(template["member_review"]["output_occurrences"])
    for member in packet_local["members"]:
        occurrence = member["occurrence"]
        proposed = "output" if occurrence in output_candidates else "housing"
        rows.append(
            "<tr>"
            f"<td><code>{html.escape(occurrence)}</code></td>"
            f"<td>{html.escape(member['related_product_name'] or '<unresolved>')}</td>"
            f"<td>{member['output_candidate_score']:+d}</td>"
            f"<td>{html.escape(member.get('member_kind', 'shape_occurrence'))}</td>"
            "<td>"
            f"<label><input type='radio' name='member-{occurrence}' value='housing' {'checked' if proposed == 'housing' else ''}> housing</label> "
            f"<label><input type='radio' name='member-{occurrence}' value='output' {'checked' if proposed == 'output' else ''}> output</label>"
            "</td></tr>"
        )
    question_rows = []
    for index, item in enumerate(template["question_responses"]):
        question_rows.append(
            f"<fieldset class='question' data-index='{index}'>"
            f"<legend>{index + 1}. {html.escape(item['question'])}</legend>"
            "<label>Resolution <select class='q-resolution'><option value='unanswered'>unanswered</option><option value='resolved'>resolved</option><option value='unresolved'>unresolved</option></select></label>"
            "<label>Response <textarea class='q-response'></textarea></label>"
            "<label>Evidence refs (one per line) <textarea class='q-evidence'></textarea></label>"
            "</fieldset>"
        )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Independent CAD review — {html.escape(source['series'])} {html.escape(source['model'])}</title>
<style>
body {{ font: 15px/1.45 system-ui, sans-serif; max-width: 1500px; margin: auto; padding: 24px; color: #18212b; background: #f5f7fa; }}
h1,h2 {{ margin-top: 1.4em; }} .warning {{ border: 2px solid #9a6700; background: #fff8c5; padding: 14px; }}
.images {{ display: grid; grid-template-columns: repeat(auto-fit,minmax(280px,1fr)); gap: 12px; }}
.images figure {{ margin: 0; background: white; padding: 8px; }} .images img {{ width: 100%; height: 360px; object-fit: contain; }}
table {{ border-collapse: collapse; width: 100%; background: white; }} th,td {{ border: 1px solid #ccd4dd; padding: 6px; text-align: left; }}
label {{ display: block; margin: 8px 0; }} textarea {{ display: block; width: 100%; min-height: 72px; }}
.question {{ margin: 14px 0; background: white; }} code,pre {{ background: #eef1f4; }} pre {{ overflow: auto; padding: 10px; }}
button {{ font-size: 16px; padding: 10px 16px; }} #status {{ white-space: pre-wrap; font-weight: 650; }}
</style>
</head>
<body>
<h1>Independent CAD review: {html.escape(source['series'])} / {html.escape(source['model'])}</h1>
<div class="warning"><strong>Candidate only.</strong> This local workbench does not grant CAD, simulator, motor, firmware, plant, HIL or robot support. It makes no network requests. A downloaded decision must pass <code>python3 tools/manage_cad_review_decisions.py --validate &lt;file&gt;</code>, then accepted geometry must be rebuilt and reverified.</div>

<h2>Exact identity</h2>
<pre>{identity}</pre>

<h2>Local evidence</h2>
<div class="images">
<figure><img src="../../review_packets/{source['variant_id']}/overview.png" alt="exact source assembly overview"><figcaption>Exact source assembly overview</figcaption></figure>
<figure><img src="../../review_packets/{source['variant_id']}/member-sheet.png" alt="isolated representative member sheet"><figcaption>Representative member sheet</figcaption></figure>
<figure><img src="../../candidate_exports/{source['variant_id']}/pose-+0deg.png" alt="candidate split at zero"><figcaption>Candidate housing/output split — zero</figcaption></figure>
<figure><img src="../../candidate_exports/{source['variant_id']}/pose--30deg.png" alt="candidate split at minus thirty degrees"><figcaption>Candidate output -30 degrees</figcaption></figure>
<figure><img src="../../candidate_exports/{source['variant_id']}/pose-+30deg.png" alt="candidate split at plus thirty degrees"><figcaption>Candidate output +30 degrees</figcaption></figure>
</div>

<h2>Occurrence membership</h2>
<table><thead><tr><th>Occurrence</th><th>STEP product</th><th>Name score</th><th>Kernel kind</th><th>Independent selection</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<label>Membership rationale <textarea id="member-rationale"></textarea></label>

<h2>Unit, frame and joint</h2>
<label>Source unit <select id="source-unit"><option>millimetre</option><option>metre</option><option>inch</option></select></label>
<label>Source axis JSON <input id="source-axis" size="40" value='{html.escape(json.dumps(template['frame_review']['source_axis_unit']))}'></label>
<label>Source origin mm JSON <input id="source-origin" size="40" value='{html.escape(json.dumps(template['frame_review']['origin_source_mm']))}'></label>
<label>Source-to-canonical 4x4 JSON <textarea id="transform">{html.escape(json.dumps(template['frame_review']['source_to_canonical']))}</textarea></label>
<label>Origin/reference-plane definition <textarea id="origin-reference">{html.escape(template['frame_review']['origin_reference'])}</textarea></label>
<label>Frame rationale <textarea id="frame-rationale"></textarea></label>
<label>Positive direction <textarea id="positive-direction">{html.escape(template['joint_review']['positive_direction'])}</textarea></label>
<label>Zero definition <textarea id="zero-definition">{html.escape(template['joint_review']['zero_definition'])}</textarea></label>
<label><input id="physical-sign" type="checkbox"> Physical motor/encoder sign has separate evidence</label>
<label>Joint rationale <textarea id="joint-rationale"></textarea></label>

<h2>Required questions</h2>
{''.join(question_rows)}

<h2>Reviewer and disposition</h2>
<label>Reviewer ID <input id="reviewer-id" size="60"></label>
<label><input id="independent" type="checkbox"> I attest that I independently inspected the exact evidence and am not the automation that generated this candidate.</label>
<label>Review assertion <textarea id="review-assertion"></textarea></label>
<label>Signature evidence refs (one per line) <textarea id="signature-refs"></textarea></label>
<label>Disposition <select id="disposition"><option value="">choose</option><option value="accept_geometry">accept geometry</option><option value="amend_candidate">amend candidate</option><option value="reject_candidate">reject candidate</option><option value="needs_more_evidence">needs more evidence</option></select></label>
<label>Redistribution <select id="redistribution"><option value="license_review_required">license review required</option><option value="local_only">local only</option><option value="redistribution_approved">redistribution approved</option><option value="redistribution_prohibited">redistribution prohibited</option></select></label>
<label>Redistribution rationale <textarea id="redistribution-rationale"></textarea></label>
<label>Redistribution evidence refs (one per line) <textarea id="redistribution-evidence"></textarea></label>
<button id="download" type="button">Validate fields and download submitted decision</button>
<div id="status" role="status"></div>

<script type="application/json" id="workbench-data">{embedded}</script>
<script>
const data = JSON.parse(document.getElementById('workbench-data').textContent);
const lines = (id) => document.getElementById(id).value.split(/\n/).map(v => v.trim()).filter(Boolean);
const value = (id) => document.getElementById(id).value.trim();
function downloadDecision() {{
  const d = structuredClone(data.template);
  const errors = [];
  d.record_state = 'submitted';
  d.reviewer = {{ reviewer_id: value('reviewer-id') || null, independence_attested: document.getElementById('independent').checked, reviewed_at: new Date().toISOString(), review_assertion: value('review-assertion') || null, signature_evidence_refs: lines('signature-refs') }};
  d.disposition = value('disposition') || null;
  if (!d.reviewer.reviewer_id || !d.reviewer.independence_attested || !d.reviewer.review_assertion) errors.push('reviewer identity, independence attestation and assertion are required');
  if (!d.disposition) errors.push('a disposition is required');
  d.member_review.housing_occurrences = [];
  d.member_review.output_occurrences = [];
  for (const member of data.members) {{
    const selected = document.querySelector(`input[name="member-${{member.occurrence}}"]:checked`);
    if (!selected) errors.push(`missing member selection ${{member.occurrence}}`);
    else d.member_review[`${{selected.value}}_occurrences`].push(member.occurrence);
  }}
  d.member_review.rationale = value('member-rationale') || null;
  d.unit_review.source_length_unit = value('source-unit');
  d.unit_review.scale_to_m = {{ millimetre: 0.001, metre: 1.0, inch: 0.0254 }}[d.unit_review.source_length_unit];
  try {{ d.frame_review.source_axis_unit = JSON.parse(value('source-axis')); }} catch {{ errors.push('source axis is not JSON'); }}
  try {{ d.frame_review.origin_source_mm = JSON.parse(value('source-origin')); }} catch {{ errors.push('source origin is not JSON'); }}
  try {{ d.frame_review.source_to_canonical = JSON.parse(value('transform')); }} catch {{ errors.push('transform is not JSON'); }}
  d.frame_review.origin_reference = value('origin-reference');
  d.frame_review.rationale = value('frame-rationale') || null;
  d.joint_review.positive_direction = value('positive-direction');
  d.joint_review.zero_definition = value('zero-definition');
  d.joint_review.physical_sign_resolved = document.getElementById('physical-sign').checked;
  d.joint_review.rationale = value('joint-rationale') || null;
  d.question_responses = [...document.querySelectorAll('.question')].map((field, index) => ({{ ...d.question_responses[index], resolution: field.querySelector('.q-resolution').value, response: field.querySelector('.q-response').value.trim() || null, evidence_refs: field.querySelector('.q-evidence').value.split(/\n/).map(v => v.trim()).filter(Boolean) }}));
  d.redistribution_review = {{ status: value('redistribution'), rationale: value('redistribution-rationale') || null, evidence_refs: lines('redistribution-evidence') }};
  const accepting = d.disposition === 'accept_geometry';
  d.semantic_review_complete = accepting;
  for (const key of ['member_review','unit_review','frame_review','joint_review']) d[key].status = accepting ? 'reviewed' : 'candidate';
  if (accepting) {{
    if (!d.member_review.rationale || !d.frame_review.rationale || !d.joint_review.rationale) errors.push('acceptance requires member, frame and joint rationales');
    for (const [index, answer] of d.question_responses.entries()) if (answer.resolution !== 'resolved' || !answer.response || !answer.evidence_refs.length) errors.push(`question ${{index + 1}} is not resolved with response/evidence`);
  }}
  d.support_granted = false;
  const status = document.getElementById('status');
  if (errors.length) {{ status.textContent = errors.join('\n'); return; }}
  const blob = new Blob([JSON.stringify(d, null, 2) + '\n'], {{ type: 'application/json' }});
  const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = `${{d.decision_id}}.json`; link.click(); URL.revokeObjectURL(link.href);
  status.textContent = 'Decision downloaded. It has not been accepted or applied; run the repository validator next.';
}}
document.getElementById('download').addEventListener('click', downloadDecision);
</script>
</body></html>
"""


def render_markdown(template: dict[str, Any], context: dict[str, Any]) -> str:
    source = context["source"]
    questions = "\n".join(
        f"{index + 1}. [ ] {item['question']} (`{item['question_sha256']}`)"
        for index, item in enumerate(template["question_responses"])
    )
    return f"""# Independent CAD review workbench — {source['series']} {source['model']}

This is a local candidate-review aid. It cannot grant CAD, simulator, motor,
plant, firmware, HIL or robot support.

- Decision: `{template['decision_id']}`
- Exact configuration: `{template['configuration_id']}`
- Exact source: `{template['variant_id']}` / `{template['source_hashes']['step_sha256']}`
- Candidate output occurrences: {', '.join(f'`{value}`' for value in template['member_review']['output_occurrences'])}
- HTML workbench: [index.html](index.html)
- Local assembly overview: [overview](../../review_packets/{source['variant_id']}/overview.png)
- Local member sheet: [member sheet](../../review_packets/{source['variant_id']}/member-sheet.png)
- Local zero-pose split: [zero pose](../../candidate_exports/{source['variant_id']}/pose-+0deg.png)

## Questions that must be resolved for acceptance

{questions}

## Submission sequence

1. Open `index.html` locally, inspect every image and occurrence, answer every
   question and download the JSON decision.
2. Validate it with `python3 tools/manage_cad_review_decisions.py --validate <file>`.
3. Place only a validated submitted decision in
   `assets/myactuator/cad_decisions/`; drafts remain generated templates.
4. An accepted geometry decision still grants no support. Rebuild and verify
   released artifacts, update the exact V2 ledger, regenerate consumers and run
   the full gate.
"""


def build(hypothesis_path: Path) -> tuple[Path, str, str]:
    template = decisions.build_template(hypothesis_path)
    context = decisions.context_for_hypothesis(hypothesis_path)
    directory = OUTPUT_ROOT / template["variant_id"]
    return directory, render_html(template, context), render_markdown(template, context)


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", type=Path)
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.write:
        directory, page, readme = build(args.write.resolve())
        atomic_write(directory / "index.html", page)
        atomic_write(directory / "README.md", readme)
        print(f"CAD_REVIEW_WORKBENCH_OK {directory.relative_to(ROOT)}")
        return 0
    hypothesis_paths = sorted((ROOT / "assets/myactuator/cad_hypotheses").glob("*.json"))
    if not hypothesis_paths:
        raise WorkbenchError("no CAD hypotheses")
    for hypothesis_path in hypothesis_paths:
        directory, page, readme = build(hypothesis_path)
        if not (directory / "index.html").is_file() or (directory / "index.html").read_text(encoding="utf-8") != page:
            raise WorkbenchError(f"workbench HTML drift: {directory.name}")
        if not (directory / "README.md").is_file() or (directory / "README.md").read_text(encoding="utf-8") != readme:
            raise WorkbenchError(f"workbench README drift: {directory.name}")
    print(f"CAD_REVIEW_WORKBENCHES_OK workbenches={len(hypothesis_paths)} support=0")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, OSError, decisions.DecisionError, WorkbenchError, ValueError) as error:
        print(f"CAD review workbench generation failed: {error}", file=os.sys.stderr)
        raise SystemExit(1)
