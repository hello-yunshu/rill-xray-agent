"""RouteAnalyzer: deterministic analysis over the safe topology projection.

The analyzer turns secret-free facts (route-topology projection, safe
observation, timeline facts, optional future RillML evidence) into a typed,
deterministic recommendation. ML may only contribute *evidence*; the analyzer
never lets ML emit arbitrary operations and never produces shell / argv /
paths.

Recommendation identity is bound to a SEMANTIC fingerprint (§22): the same
semantic problem must not yield a fresh recommendation id merely because the
capture timestamp changed (otherwise the 30-minute same-recommendation
cooldown is meaningless). The fingerprint binds only:
  - normalized topology semantics (predicate digests, rule count, managed set)
  - recommendation type
  - operations semantics
  - relevant config generation / source hash

Design:
  - recommendationType is a small fixed enum (shadowed / unreachable /
    managed-rule-added / none / stale).
  - RoutePlanner turns recommendationType -> typed operations deterministically.
"""
from __future__ import annotations

import hashlib
import time
import uuid

from .canonical import canonical_bytes, digest
from .route_contract import AUTO_MAX_RISK

# Recommendation types the deterministic analyzer can emit. These are the only
# values the planner understands; ML evidence can only influence the score.
RECOMMENDATION_TYPES = frozenset({
    'managed-rule-shadowed',   # a Rill-managed rule is shadowed by an earlier rule
    'unreachable-rule',        # a managed rule can never match (catch-all order)
    'managed-rule-added',      # a managed rule is present (v1 keeps it minimal)
    'stale-topology',          # topology is stale / can't produce a plan
    'no-recommendation',       # nothing actionable
})

# Confidence bands (deterministic, not probabilities).
CONFIDENCE_BANDS = frozenset({'high', 'medium', 'low'})


def semantic_fingerprint(recommendation_type, operations_semantics,
                         config_generation=None, source_config_sha256=None):
    """Stable fingerprint across re-captures of the same semantic situation.

    Binds (§22):
      - normalized topology semantics (via operations_semantics)
      - recommendation type
      - relevant config generation / source hash
    Excludes created/captured timestamps so the 30-minute same-recommendation
    cooldown stays meaningful.
    """
    material = hashlib.sha256(canonical_bytes({
        'recommendationType': recommendation_type,
        'operationsSemantics': operations_semantics,
        'configGeneration': config_generation,
        'sourceConfigSha256': source_config_sha256,
    })).hexdigest()
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, material))


class RouteAnalyzer:
    """Input: safe projection dict (from RouteTopologyProjection.project()),
    plus optional safe observation facts. Output: a Recommendation dict.

    The analyzer never sees raw config text and never returns operations; it
    only classifies the situation. It is deterministic for identical inputs.
    """

    def __init__(self, topology_projection, observation=None, timeline_facts=None,
                 rillml_evidence=None, now=None):
        self.topology = topology_projection if isinstance(topology_projection, dict) else {}
        self.rules = self.topology.get('rules') or []
        self.observation = observation if isinstance(observation, dict) else {}
        self.timeline_facts = timeline_facts if isinstance(timeline_facts, dict) else {}
        self.evidence = rillml_evidence if isinstance(rillml_evidence, dict) else {}
        self._now = int(now if now is not None else time.time())
        # Rule objects are already secret-free (digests only).
        self._managed_indexes = [r['ruleIndex'] for r in self.rules if r.get('isManaged')]

    def _semantics(self):
        """Normalized topology semantics used for the semantic fingerprint:
        ordered predicate digests + rule count + managed set. Timestamp and
        whole-config digest are intentionally excluded where not relevant."""
        ordered = [r.get('predicateDigest') for r in self.rules]
        return {
            'orderedPredicates': ordered,
            'ruleCount': len(self.rules),
            'managedIndexes': self._managed_indexes,
        }

    def _recommendation(self, rtype, risk, reason_code, ops_semantics, extra=None):
        rec = {
            'recommendationType': rtype,
            'confidenceBand': 'high',
            'risk': risk,
            'reasonCode': reason_code,
            'evidenceDigest': digest({
                'semantics': self._semantics(),
                'recommendationType': rtype,
                'operationsSemantics': ops_semantics,
                'sourceConfigSha256': self.topology.get('wholeConfigSha256', ''),
                'configGeneration': self.topology.get('configGeneration', 0),
            }),
            'createdAtEpochSeconds': self._now,
        }
        if extra:
            rec.update(extra)
        rec['semanticFingerprint'] = self.semantic_fingerprint(rtype, ops_semantics)
        rec['recommendationId'] = rec['semanticFingerprint']
        return rec

    @staticmethod
    def semantic_fingerprint(recommendation_type, operations_semantics,
                             config_generation=None, source_config_sha256=None):
        """Fingerprint that is stable across re-captures of the same semantic
        situation. Excludes created/captured timestamps."""
        return semantic_fingerprint(recommendation_type, operations_semantics,
                                    config_generation, source_config_sha256)

    def analyze(self):
        """Deterministic classification. Returns a recommendation dict or
        raises ValueError for invalid inputs."""
        if not isinstance(self.topology, dict) or 'rules' not in self.topology:
            raise ValueError('analyzer requires a safe topology projection')
        shadowed = self._shadowing_analysis()
        if shadowed:
            return self._recommendation(
                'managed-rule-shadowed', 'low',
                'managed-rule-shadowed:' + ','.join(
                    f'{s}<{b}' for s, b in sorted(shadowed.items())),
                {'managedShadowed': sorted(shadowed.items())},
                extra={'shadowing': shadowed})
        # No managed rule to shadow: nothing actionable in v1.
        return self._recommendation(
            'no-recommendation', 'low',
            'no-actionable-managed-route-situation',
            {'managedIndexes': self._managed_indexes})

    def _shadowing_analysis(self):
        """Detect Rill-managed rules that are exactly shadowed by an earlier
        rule (same selector predicate: selector types + per-field digests).
        Xray routes on the first matching rule, so the outbound tag does not
        participate: two rules with the same selector predicate are a
        shadowing situation even with different outbound targets."""
        seen = {}
        shadowed = {}
        for r in self.rules:
            idx = r.get('ruleIndex')
            key = digest({
                'selectorTypes': r.get('selectorTypes'),
                'selectorDigests': r.get('selectorDigests'),
            })
            if key in seen:
                shadowed[idx] = seen[key]
            else:
                seen[key] = idx
        return {s: b for s, b in shadowed.items() if s in self._managed_indexes}


def auto_eligible(recommendation):
    """Auto V1 gate: only low-risk recommendations are auto-eligible, and only
    when the recommendation is within the auto allowlist. The root executor
    re-evaluates independently; this is the analyzer-level surface."""
    if not isinstance(recommendation, dict):
        return False
    rtype = recommendation.get('recommendationType')
    if rtype not in ('managed-rule-shadowed', 'managed-rule-added'):
        return False
    return recommendation.get('risk') == AUTO_MAX_RISK
