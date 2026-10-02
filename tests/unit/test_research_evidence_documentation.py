"""Navigation integrity for the implemented producer-to-reader walkthrough."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
OPS = ROOT / 'docs/operations/research-evidence-delivery.md'
ADR = ROOT / 'docs/decisions/research-findings-delivery-authority.md'
PROOF = ROOT / 'docs/evidence/research-evidence-delivery-v1.md'


def local_link_targets(path):
    for target in re.findall(r'\]\(([^)]+)\)', path.read_text(encoding='utf-8')):
        if '://' not in target and not target.startswith('#'):
            yield (path.parent / target.split('#', 1)[0]).resolve()


def test_walkthrough_and_evidence_have_resolvable_bidirectional_discovery():
    for entry in (ROOT / 'README.md', ROOT / 'README_CN.md', ROOT / 'docs/README.md'):
        targets = set(local_link_targets(entry))
        assert OPS in targets
        assert PROOF in targets
    assert ADR in set(local_link_targets(ROOT / 'docs/README.md'))
    assert OPS in set(local_link_targets(PROOF))
    assert PROOF in set(local_link_targets(OPS))
    assert ADR in set(local_link_targets(OPS))
    for document in (OPS, PROOF, ADR):
        for target in local_link_targets(document):
            assert target.is_file(), f'{document.name} has a broken local target: {target.name}'


def test_walkthrough_code_navigation_resolves_actual_source_files():
    navigation = OPS.read_text(encoding='utf-8').split('## Bounds and navigation', 1)[1].split('## Separate proposed', 1)[0]
    paths = re.findall(r'`((?:agent|api|frontend|scripts|tests)/[^`]+)`', navigation)
    assert paths
    for path in paths:
        relative = path.split('::', 1)[0]
        assert (ROOT / relative).is_file(), relative
