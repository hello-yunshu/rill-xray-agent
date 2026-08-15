"""Safe, secret-free projection of Xray routing topology.

The projection is produced by the root observer and consumed read-only by the
unprivileged Runtime. It MUST never leak UUID / privateKey / shortId / Reality
material / proxy URLs / VLESS links / raw config bodies / client credentials.

Rule predicates are persisted as digests only. Every selector field present in
a rule participates (multi-selector): shadowing / ordering / reachability
analysis is computed on the FULL predicate, never on "the first selector".

Schema v2 (this module):
  rule: {
    ruleIndex, ruleKind, position,
    selectorTypes: [..],            # ordered, distinct selector field names
    selectorDigests: {field: sha256},# per-field digest of the (safe) value
    predicateDigest: sha256,         # whole-predicate digest (selector types +
                                     # per-field digests + outboundTag digest)
    outboundTag,                     # safe role string or ''
    hasCatchAll,                     # rule with no usable selector value
    isManaged
  }
"""
import hashlib
import json
import time

from .canonical import digest
from .route_contract import MANAGED_PREFIX

_SELECTOR_KEYS = ('domain', 'ip', 'network', 'port', 'protocol', 'source',
                  'inboundTag', 'user', 'email')

# Fields that never go into the digest because they are secret-bearing or
# would make the projection reversible (selector VALUES are always digested).
_SAFE_ENUM_FIELDS = ('protocol', 'network', 'port')


def _is_secret_selector(field):
    """Selectors that could carry secret/credential material are never
    persisted in clear even as enums; only a digest is allowed."""
    return field in ('user', 'email', 'source')


def _kind(rule):
    if isinstance(rule.get('domain'), (list, str)):
        return 'domain'
    if isinstance(rule.get('ip'), (list, str)):
        return 'ip'
    if rule.get('type') == 'field' or any(k in rule for k in _SELECTOR_KEYS):
        return 'field'
    return 'other'


def _selector_fields(rule):
    """Ordered, distinct selector field names present in the rule."""
    fields = []
    for k in _SELECTOR_KEYS:
        v = rule.get(k)
        if v is not None and not (isinstance(v, (list, str, int)) and v == []):
            fields.append(k)
    return fields


def _selector_value_digest(field, value):
    """Digest of a selector value. Enum-like values (protocol/network/port)
    are digested from their canonical scalar too, so the projection remains
    non-reversible and uniformly shaped."""
    if isinstance(value, list):
        items = [json.dumps(x, sort_keys=True, ensure_ascii=False) for x in value]
        material = ';'.join(sorted(items))
    else:
        material = str(value)
    return digest({'field': field, 'value': material})


def selector_value_digest(field, value):
    """Public alias: the digest of a selector VALUE.

    Shared by the root observer (projection) and the analyzer (managed-route
    intent drift detection) so both compute the SAME per-field digest for the
    same selector value. The digest is non-reversible: selector VALUES are
    never persisted in clear by the projection.
    """
    return _selector_value_digest(field, value)


def _outbound_tag_digest(value):
    return digest({'outboundTag': value if isinstance(value, str) else ''})


def _managed(rule):
    tag = rule.get('tag')
    return isinstance(tag, str) and tag.startswith(MANAGED_PREFIX)


def _has_catch_all(rule, fields):
    if not fields:
        return True
    return False


class RouteTopologyProjection:
    def __init__(self, routing, config_generation=0, whole_config_safe_digest=None,
                 captured_at_epoch_seconds=None):
        self._routing = routing if isinstance(routing, dict) else {}
        self._generation = int(config_generation)
        self._whole_digest = whole_config_safe_digest
        self._captured_at = (int(captured_at_epoch_seconds)
                             if captured_at_epoch_seconds is not None
                             else int(time.time()))
        rules = self._routing.get('rules')
        self._rules = rules if isinstance(rules, list) else []

    @staticmethod
    def ownership_marker():
        return MANAGED_PREFIX + hashlib.sha256(
            b'rill-xray-agent-ownership').hexdigest()[:6]

    def managed_rules(self):
        return [i for i, r in enumerate(self._rules) if _managed(r)]

    def _safe_rule(self, index, rule, position):
        fields = _selector_fields(rule)
        selectors = {f: _selector_value_digest(f, rule.get(f)) for f in fields}
        outbound = rule.get('outboundTag', '')
        predicate = {
            'selectorTypes': fields,
            'selectorDigests': selectors,
            'outboundTagDigest': _outbound_tag_digest(outbound),
        }
        managed = _managed(rule)
        safe = {
            'ruleIndex': index,
            'ruleKind': _kind(rule),
            'position': position,
            'selectorTypes': fields,
            'selectorDigests': selectors,
            'predicateDigest': digest(predicate),
            'outboundTag': outbound if isinstance(outbound, str) else '',
            'hasCatchAll': not fields,
            'isManaged': managed,
        }
        if managed:
            # Secret-free managed-rule identity: digest of the Rill-owned tag.
            # Enables the analyzer to match a root-authoritative intent rule to
            # its live rule WITHOUT persisting the raw tag in clear.
            tag = rule.get('tag')
            safe['managedId'] = digest({'managedTag': tag if isinstance(tag, str) else ''})
        return safe

    def project(self):
        rules = [self._safe_rule(i, r, p)
                 for p, (i, r) in enumerate(enumerate(self._rules))]
        d = self._whole_digest or ''
        gen = self._generation
        return {
            'schemaVersion': 2,
            'capturedAtEpochSeconds': self._captured_at,
            # Canonical public field name (P0-7): generation is root-owned
            # authority. ``configGeneration`` remains ONLY as a deprecated
            # migration alias for older consumers; new schema never double-writes
            # both as separate truths.
            'configurationGeneration': gen,
            'configGeneration': gen,
            'wholeConfigSha256': d,
            'wholeConfigSafeDigest': d,
            'routingRulesCount': len(self._rules),
            'rules': rules,
        }

    def unreachable_rules(self):
        """Return {shadowedIndex: shadowingIndex} for rules whose FULL
        predicate is exactly shadowed by an earlier rule. Uses the predicate
        digest so multi-selector rules compare correctly."""
        seen = {}
        shadowed = {}
        for i, r in enumerate(self._rules):
            fields = _selector_fields(r)
            if not fields:
                continue
            predicate = {
                'selectorTypes': fields,
                'selectorDigests': {f: _selector_value_digest(f, r.get(f))
                                    for f in fields},
            }
            key = digest(predicate)
            if key in seen:
                shadowed[i] = seen[key]
            else:
                seen[key] = i
        return shadowed
