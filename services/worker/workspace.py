"""Validation for studio campaign metadata and unpublished identity boards.

Source paths are provenance labels only. Nothing here opens, serves or fetches
a path or URL supplied by a board. Publishing remains an explicit API action.
"""
import copy
import json
import math
from urllib.parse import urlsplit


class WorkspaceConflict(ValueError):
    """A stale edit, publication or incompatible project assignment."""


def text(value, field, limit=300):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f'{field} must be nonempty text (at most {limit} characters)')
    return value.strip()


def string_list(value, field, limit=100):
    if not isinstance(value, list) or len(value) > limit:
        raise ValueError(f'{field} must be an array of at most {limit} strings')
    result = [text(v, field) for v in value]
    if len(result) != len(set(result)):
        raise ValueError(f'{field} must not contain duplicates')
    return result


def campaign_fields(payload, *, partial=False):
    if not isinstance(payload, dict):
        raise ValueError('campaign must be an object')
    allowed = {'name', 'brand', 'ranges', 'status'}
    if set(payload) - allowed:
        raise ValueError('unknown campaign fields: ' + ', '.join(sorted(set(payload) - allowed)))
    result = {}
    for field in ('name', 'brand'):
        if field in payload or not partial:
            result[field] = text(payload.get(field), field)
    if 'ranges' in payload or not partial:
        result['ranges'] = string_list(payload.get('ranges', []), 'ranges')
    if 'status' in payload or not partial:
        result['status'] = payload.get('status', 'active')
        if result['status'] not in ('active', 'archived'):
            raise ValueError('campaign status must be active or archived')
    return result


def revision_number(value, field='expected_revision'):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f'{field} must be a nonnegative integer')
    return value


def design_markdown(profile):
    """Canonical interpretive guidance for the reviewed identity package.

    Mirrors the identity-board export in services/ui/src/identity.ts. Source
    transcriptions stay evidence on the board; working swatches define colour.
    Draft/rejected cards and review/provenance metadata never become guidance.
    """
    identity = profile.get('identity') or {}
    lines = [f"# {identity.get('brandName') or profile.get('name', '')} — design guidance", '',
             f"Campaign: {identity['campaignName']}" if identity.get('campaignName') else '',
             'Apply guidance only within its stated campaign, range and channel. Provisional interpretations are for internal review; reviewed interpretations are not client artwork approval. Draft and rejected cards are excluded. Numeric rules are enforced only where the application implements the corresponding validator.', '',
             '## Published-package colour definitions', '']
    for swatch in profile.get('swatches', []):
        values = ' / '.join(format(v, 'g') if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v)
                            for v in swatch.get('values', []))
        lines.append(f"- {swatch['name']}: {swatch.get('space', '').upper()} {values}" + (' (spot)' if swatch.get('spot') else ''))
    lines += ['', '## Font references', '']
    lines += ['- ' + font for font in profile.get('fonts', [])]
    lines += ['', '## Creative guidance', '']
    for card in identity.get('cards', []):
        if card.get('status') not in ('reviewed', 'provisional') or card.get('origin') == 'extracted-colour-values':
            continue
        lines += [f"### {card['title']} [{card['id']}]",
                  f"Scope: {card.get('scope') or 'Unspecified'} · Status: {card['status']}",
                  '', card['body'], '']
        if card.get('conditions'):
            conditions = card['conditions']
            lines += ['Conditions: ' + ('; '.join(conditions) if isinstance(conditions, list) else conditions), '']
        if card.get('source'):
            source = card['source']
            lines += ['Source: ' + source.get('label', '') + (f", page {source['page']}" if source.get('page') else ''), '']
    return '\n'.join(line for i, line in enumerate(lines) if line != '' or i == 0 or lines[i - 1] != '')


def model_design_principles(profile):
    """Use reviewed cards even for older snapshots containing stale Markdown.

    apply_overrides appends explicit project instructions to a list whose first
    element is the published base. Preserve that suffix only when its base is
    still the current canonical board guidance. Unrecognized stale prose is
    never recovered from the profile's other metadata.
    """
    previous = profile.get('designPrinciples')
    if isinstance(profile.get('identity'), dict):
        canonical = design_markdown(profile)
        if isinstance(previous, list) and previous and previous[0] == canonical:
            extra = [entry for entry in previous[1:] if isinstance(entry, str) and entry.strip()]
            if extra:
                canonical += '\n\n## Explicit project guidance\n\n' + '\n\n'.join(extra)
        return canonical
    if isinstance(previous, list):
        return '\n\n'.join(entry for entry in previous if isinstance(entry, str))
    return previous


def _validate_working_definitions(profile):
    """Validate working values without rewriting source evidence or metadata."""
    seen = set()
    for swatch in profile['swatches']:
        if not isinstance(swatch, dict):
            raise ValueError('working swatches must be objects')
        name = text(swatch.get('name'), 'swatch.name')
        if name.lower() in seen:
            raise ValueError('working swatch names must be unique (ignoring case and outer spaces)')
        seen.add(name.lower())
        space = swatch.get('space')
        if space not in ('rgb', 'cmyk'):
            raise ValueError('swatch.space must be rgb or cmyk')
        count, maximum = (3, 255) if space == 'rgb' else (4, 100)
        values = swatch.get('values')
        if not isinstance(values, list) or len(values) != count:
            raise ValueError(f'{space.upper()} swatches need exactly {count} channel values')
        for value in values:
            # Range-check before isfinite so arbitrarily large JSON integers
            # are rejected without overflowing Python's float conversion.
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not 0 <= value <= maximum or not math.isfinite(value)):
                raise ValueError(f'{space.upper()} channels must be finite numbers between 0 and {maximum}')
    fonts = profile.get('fonts', [])
    if not isinstance(fonts, list):
        raise ValueError('profile.fonts must be an array of font reference strings')
    seen = set()
    for font in fonts:
        name = text(font, 'font reference')
        if name.lower() in seen:
            raise ValueError('font references must be unique (ignoring case and outer spaces)')
        seen.add(name.lower())


def identity_profile(name, profile):
    if not isinstance(profile, dict) or not isinstance(profile.get('swatches'), list):
        raise ValueError('identity draft needs a profile with a swatches array')
    result = copy.deepcopy(profile)
    if result.get('name', name) != name:
        raise ValueError('draft profile name must match its brand')
    result['name'] = name
    try:
        encoded = json.dumps(result, allow_nan=False)
    except (TypeError, ValueError):
        raise ValueError('profile must contain valid JSON values') from None
    if len(encoded.encode()) > 2_000_000:
        raise ValueError('identity draft exceeds 2 MB')
    _validate_working_definitions(result)
    identity = result.get('identity')
    if not isinstance(identity, dict):
        raise ValueError('profile.identity must contain the identity board')
    if identity.get('schemaVersion') != 1 or isinstance(identity.get('schemaVersion'), bool):
        raise ValueError('identity.schemaVersion must be 1')
    # A board's display label can be shorter than the canonical legacy brand
    # key. Routing and publication identity remain locked by profile.name.
    text(identity.get('brandName'), 'identity.brandName')
    if 'ranges' in identity:
        string_list(identity['ranges'], 'identity.ranges')
    cards = identity.get('cards')
    if not isinstance(cards, list) or len(cards) > 500:
        raise ValueError('identity.cards must be an array of at most 500 cards')
    ids = set()
    categories = {'colour', 'typography', 'logo', 'imagery', 'composition', 'copy', 'guidance'}
    for card in cards:
        if not isinstance(card, dict):
            raise ValueError('identity cards must be objects')
        card_id = text(card.get('id'), 'card.id')
        if card_id in ids:
            raise ValueError('identity card IDs must be unique')
        ids.add(card_id)
        if card.get('category') not in categories:
            raise ValueError('unknown identity card category')
        if card.get('status') not in ('draft', 'reviewed', 'provisional', 'rejected'):
            raise ValueError('unknown identity card review status')
        text(card.get('title'), 'card.title')
        if not isinstance(card.get('body'), str):
            raise ValueError('card.body must be text')
        if 'scope' in card and not isinstance(card['scope'], str):
            raise ValueError('card.scope must be text')
        conditions = card.get('conditions')
        if conditions is not None and not (isinstance(conditions, str) or
                isinstance(conditions, list) and all(isinstance(c, str) for c in conditions)):
            raise ValueError('card.conditions must be text or an array of text')
        if 'assetNames' in card:
            string_list(card['assetNames'], 'card.assetNames')
        source = card.get('source')
        if source is not None:
            if not isinstance(source, dict):
                raise ValueError('card.source must be an object')
            for field in ('label', 'path', 'sha256'):
                if field in source and not isinstance(source[field], str):
                    raise ValueError('source.' + field + ' must be text')
            if 'page' in source and (isinstance(source['page'], bool) or not isinstance(source['page'], int) or source['page'] < 1):
                raise ValueError('source.page must be a positive integer')
            if 'url' in source:
                url = source['url']
                if not isinstance(url, str):
                    raise ValueError('source.url must be an HTTPS/HTTP link')
                parsed = urlsplit(url)
                registered_local = (not parsed.scheme and not parsed.netloc
                                    and parsed.path.startswith(('/api/brands/', '/brands/'))
                                    and '/sources/' in parsed.path
                                    and '..' not in parsed.path.split('/') and '\\' not in parsed.path)
                remote = parsed.scheme in ('https', 'http') and bool(parsed.hostname) and not parsed.username and not parsed.password
                if (not registered_local and not remote) or any(ord(c) < 32 for c in url):
                    raise ValueError('source.url must be an HTTPS/HTTP link without credentials')
        review = card.get('review')
        if review is not None and (not isinstance(review, dict) or review.get('clientApproval') is not False):
            raise ValueError('studio identity review must explicitly set clientApproval: false')
    result['designPrinciples'] = design_markdown(result)
    return result
