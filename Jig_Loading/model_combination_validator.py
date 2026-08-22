"""
Model Combination Validator — DB-driven eligibility check for Jig Loading "Add Model" flow.

Architecture:
- Eligibility is determined by backend master data only (single source of truth):
  ModelMicroGroup plus explicit same/ditto model relationships.
- No prefix-based hardcoding. No color codes.
- Frontend renders; backend decides which models are eligible.
- New groups / models are added via Django admin — zero code changes required.

Flow:
    1. Receive selected_models (list of plating_stk_nos already on the jig).
    2. Use the primary model (selected_models[0]) to find its micro group.
    3. Fetch all active models from that micro group.
    4. Also allow the exact same PSN and explicit same/ditto LookLikeModel relations.
    5. Return eligible_models list (compatible response format for existing frontend).
"""
import logging

logger = logging.getLogger(__name__)


def _normalise_psns(psns):
    """Return unique, non-empty PSNs in the original order."""
    if isinstance(psns, str):
        psns = [psns]
    normalised = []
    seen = set()
    for psn in psns or []:
        value = str(psn or '').strip()
        if value and value not in seen:
            normalised.append(value)
            seen.add(value)
    return normalised


def _add_psn(target, seen, psn):
    value = str(psn or '').strip()
    if value and value not in seen:
        target.append(value)
        seen.add(value)


def _get_same_model_psns(seed_psns):
    """Fetch explicit same/ditto PSNs from LookLikeModel in both directions."""
    seed_psns = _normalise_psns(seed_psns)
    if not seed_psns:
        return []

    try:
        from django.db.models import Q
        from modelmasterapp.models import LookLikeModel, ModelMaster

        master_ids = list(
            ModelMaster.objects.filter(plating_stk_no__in=seed_psns)
            .values_list('id', flat=True)
        )
        if not master_ids:
            return []

        same_psns = []
        seen = set()
        look_like_rows = (
            LookLikeModel.objects.filter(
                Q(same_plating_stk_no_id__in=master_ids) |
                Q(plating_stk_no__id__in=master_ids)
            )
            .select_related('same_plating_stk_no')
            .prefetch_related('plating_stk_no')
            .distinct()
        )

        for row in look_like_rows:
            _add_psn(same_psns, seen, getattr(row.same_plating_stk_no, 'plating_stk_no', ''))
            for related_master in row.plating_stk_no.all():
                _add_psn(same_psns, seen, getattr(related_master, 'plating_stk_no', ''))

        return same_psns
    except Exception as exc:
        logger.exception('[VALIDATE] Failed to fetch same/ditto model PSNs: %s', exc)
        return []


def resolve_add_model_eligible_psns(primary_psn, selected_models=None):
    """Resolve Add Model eligible PSNs from backend master data.

    The exact primary PSN is intentionally included. The filter screen already
    excludes selected lots by lot_id, so keeping the PSN allows another accepted
    lot of the same/ditto model to be added.
    """
    selected_psns = _normalise_psns(selected_models)
    primary_psn = str(primary_psn or '').strip()
    if not primary_psn and selected_psns:
        primary_psn = selected_psns[0]
    if not primary_psn:
        return [], []

    eligible_psns = []
    seen = set()
    _add_psn(eligible_psns, seen, primary_psn)

    try:
        from Jig_Loading.models import ModelMicroGroup

        group_entry = ModelMicroGroup.objects.filter(
            plating_stk_no=primary_psn,
            is_active=True,
        ).first()
        if group_entry:
            for psn in ModelMicroGroup.objects.filter(
                group_name=group_entry.group_name,
                is_active=True,
            ).values_list('plating_stk_no', flat=True):
                _add_psn(eligible_psns, seen, psn)
            logger.info('[VALIDATE] primary_psn=%s group_name=%s', primary_psn, group_entry.group_name)
        else:
            logger.info('[VALIDATE] primary_psn=%s has no micro group; allowing same/ditto only', primary_psn)
    except Exception as exc:
        logger.exception('[VALIDATE] Failed to fetch micro-group PSNs: %s', exc)

    for psn in _get_same_model_psns([primary_psn]):
        _add_psn(eligible_psns, seen, psn)

    invalid_selected = [psn for psn in selected_psns if psn not in seen]
    if invalid_selected:
        return eligible_psns, invalid_selected

    for psn in _get_same_model_psns(selected_psns):
        _add_psn(eligible_psns, seen, psn)

    return eligible_psns, []


def validate_model_combination(selected_models):
    """
    Determine which models are eligible to add alongside the already-selected models.

    Args:
        selected_models: list of plating_stk_no strings currently on the jig.
                         selected_models[0] is treated as the primary model.

    Returns dict (backward-compatible format):
        {
            'eligible_models':               [{'plating_stk_no', 'model_no', 'ep_bath_type', 'jig_capacity'}, ...],
            'non_eligible_models':           [],
            'blocked_lookalike_plating_stk_nos': [],
            'warnings':                      [],
            'errors':                        [],
        }
    """
    eligible_models = []
    errors = []

    if not selected_models:
        errors.append('No models selected.')
        logger.warning('[VALIDATE] Called with empty selected_models')
        return _make_response(eligible_models, errors)

    selected_models = [s.strip() for s in selected_models if s and s.strip()]
    primary_psn = selected_models[0]

    logger.info(f'[VALIDATE] primary_psn={primary_psn} selected_models={selected_models}')

    try:
        from modelmasterapp.models import ModelMaster

        eligible_psns, invalid_selected = resolve_add_model_eligible_psns(primary_psn, selected_models)
        if invalid_selected:
            logger.warning(
                '[VALIDATE] Compatibility mismatch selected_models=%s invalid=%s',
                selected_models,
                invalid_selected,
            )
            errors.append('No compatible models found')
            return _make_response(eligible_models, errors)

        logger.info(f'[VALIDATE] eligible_psns={eligible_psns}')

        if not eligible_psns:
            errors.append('No compatible models found')
            return _make_response(eligible_models, errors)

        # Enrich with ModelMaster display data (model_no, ep_bath_type)
        mm_lookup = {
            mm['plating_stk_no']: mm
            for mm in ModelMaster.objects.filter(
                plating_stk_no__in=eligible_psns
            ).values('plating_stk_no', 'model_no', 'ep_bath_type')
        }

        for psn in eligible_psns:
            mm = mm_lookup.get(psn, {})
            eligible_models.append({
                'plating_stk_no': psn,
                'model_no': mm.get('model_no', ''),
                'ep_bath_type': mm.get('ep_bath_type', ''),
                'jig_capacity': 0,
            })

        # Sort: put models registered in ModelMaster first, then by plating_stk_no
        eligible_models.sort(key=lambda m: (0 if m['model_no'] else 1, m['plating_stk_no']))

        logger.info(f'[VALIDATE] Result: eligible={len(eligible_models)} errors={errors}')

    except Exception as e:
        logger.exception(f'[VALIDATE] Unhandled exception: {e}')
        errors.append(f'Eligibility check failed: {str(e)}')

    return _make_response(eligible_models, errors)


def _make_response(eligible_models, errors=None):
    """Return backward-compatible response dict."""
    return {
        'eligible_models': eligible_models,
        'non_eligible_models': [],
        'blocked_lookalike_plating_stk_nos': [],
        'warnings': [],
        'errors': errors or [],
    }
