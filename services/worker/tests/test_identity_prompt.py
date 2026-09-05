"""Reviewed board decisions are authoritative; archived evidence is not."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from brand import apply_overrides
from generation.prompts import assets_section, build_system
from store import DocStore
from workspace import design_markdown, identity_profile


def board():
    cards = [
        {'id': 'D01', 'category': 'guidance', 'title': 'Working choice', 'status': 'reviewed', 'body': 'CURRENT_REVIEWED_DIRECTION', 'scope': 'Prime Forever', 'conditions': ['Internal only', 'Portrait'], 'source': {'label': 'Campaign BVI', 'page': 4}},
        {'id': 'D02', 'category': 'guidance', 'title': 'Working assumption', 'status': 'provisional', 'body': 'CURRENT_PROVISIONAL_DIRECTION', 'scope': 'Shared'},
        {'id': 'D03', 'category': 'guidance', 'title': 'REJECTED_TITLE', 'status': 'rejected', 'body': 'REJECTED_TRIAL_DIRECTION', 'scope': 'REJECTED_SCOPE', 'source': {'label': 'REJECTED_SOURCE'}},
        {'id': 'D04', 'category': 'guidance', 'title': 'DRAFT_TITLE', 'status': 'draft', 'body': 'DRAFT_DIRECTION', 'scope': 'DRAFT_SCOPE'},
        {'id': 'C01', 'category': 'colour', 'title': 'EXTRACTED_COLOUR_TITLE', 'status': 'reviewed', 'origin': 'extracted-colour-values', 'body': 'OUTDATED_SOURCE_COLOUR_VALUES', 'scope': 'Shared'},
    ]
    return {'name': 'Brand', 'version': '1', 'swatches': [{'name': 'Working violet', 'space': 'cmyk', 'values': [35, 25, 13, 1], 'source': 'HIDDEN_SWATCH_METADATA'}],
            'fonts': ['Effra Bold'], 'charStyles': [{'name': 'Headline', 'font': 'Effra Bold', 'size': 24}],
            'paraStyles': [{'name': 'Left', 'charStyle': 'Headline', 'align': 'left'}],
            'rules': {'minTypeSize': 8, 'safeZone': True, 'mandatoryElements': ['logo'], 'sourceNotes': 'HIDDEN_RULE_METADATA'},
            'identity': {'schemaVersion': 1, 'brandName': 'Brand', 'campaignName': 'Campaign', 'cards': cards, 'provenance': {'oldDecision': 'HIDDEN_IDENTITY_PROVENANCE'}},
            'designPrinciples': 'STALE_CLIENT_MARKDOWN', 'trialDecisions': [{'id': 'D01', 'body': 'SUPERSEDED_D01'}, {'id': 'D03', 'body': 'REJECTED_TRIAL_DIRECTION'}],
            'reviewedRuleIds': ['HIDDEN_RULE_IDS'], 'provenance': {'note': 'HIDDEN_PROFILE_PROVENANCE'},
            'assetNotes': [{'name': 'product', 'description': 'ASSET_SEMANTIC_DESCRIPTION', 'notes': 'HIDDEN_ASSET_REVIEW_METADATA'}]}


def system(profile):
    return build_system({'system_text': 'Core system'}, {'type': 'object'}, profile, {})


class IdentityPromptTests(unittest.TestCase):
    def test_locked_machine_block_has_only_runtime_fields(self):
        block = next(b['text'] for b in system(board()) if b['text'].startswith('## Brand profile'))
        machine = json.loads(block.split('\n\n', 1)[1])
        self.assertEqual(set(machine), {'name', 'version', 'swatches', 'fonts', 'charStyles', 'paraStyles', 'rules'})
        self.assertEqual(machine['swatches'][0], {'name': 'Working violet', 'space': 'cmyk', 'values': [35, 25, 13, 1]})
        self.assertEqual(machine['rules'], {'minTypeSize': 8, 'safeZone': True, 'mandatoryElements': ['logo']})

    def test_no_rejected_draft_or_superseded_text_in_any_system_block(self):
        text = '\n'.join(b['text'] for b in system(board()))
        for banned in ['REJECTED_', 'DRAFT_', 'SUPERSEDED_D01', 'STALE_CLIENT_MARKDOWN',
                       'HIDDEN_', 'ASSET_SEMANTIC_DESCRIPTION', 'EXTRACTED_COLOUR_TITLE', 'OUTDATED_SOURCE_COLOUR_VALUES']:
            self.assertNotIn(banned, text)
        self.assertIn('CURRENT_REVIEWED_DIRECTION', text)
        self.assertIn('CURRENT_PROVISIONAL_DIRECTION', text)
        self.assertIn('Scope: Prime Forever · Status: reviewed', text)
        self.assertIn('Conditions: Internal only; Portrait', text)
        self.assertIn('Source: Campaign BVI, page 4', text)

    def test_source_colour_transcription_preserved_but_not_applied(self):
        profile = identity_profile('Brand', board())
        self.assertEqual(profile['identity']['cards'][-1]['body'], 'OUTDATED_SOURCE_COLOUR_VALUES')
        self.assertNotIn('OUTDATED_SOURCE_COLOUR_VALUES', profile['designPrinciples'])
        self.assertIn('Working violet: CMYK 35 / 25 / 13 / 1', profile['designPrinciples'])
        profile['swatches'][0]['values'] = [36, 26, 14, 2]
        changed = identity_profile('Brand', profile)
        self.assertIn('Working violet: CMYK 36 / 26 / 14 / 2', changed['designPrinciples'])
        self.assertEqual(changed['identity']['cards'][-1]['body'], 'OUTDATED_SOURCE_COLOUR_VALUES')

    def test_save_and_publish_rederive_guidance_after_edit_and_rejection(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = DocStore(Path(temporary) / 'board.db')
            original = store.save_brand_profile('Brand', board())
            draft = board()
            draft['identity']['cards'][0]['body'] = 'EDITED_D01_DIRECTION'
            saved = store.save_identity_draft('Brand', draft, expected_revision=0)
            self.assertIn('EDITED_D01_DIRECTION', saved['profile']['designPrinciples'])
            self.assertNotIn('STALE_CLIENT_MARKDOWN', saved['profile']['designPrinciples'])
            self.assertEqual(store.get_brand_profile('Brand')['id'], original['id'])
            draft = saved['profile']
            draft['identity']['cards'][0]['status'] = 'rejected'
            # Publication now requires a review outcome for every draft card.
            # The separate prompt-leak test still covers exclusion of drafts.
            for card in draft['identity']['cards']:
                if card['status'] == 'draft':
                    card['status'] = 'rejected'
            # Simulate a client sending obsolete Markdown and old trial notes.
            draft['designPrinciples'] += '\nEDITED_D01_DIRECTION'
            saved = store.save_identity_draft('Brand', draft, expected_revision=1)
            self.assertNotIn('EDITED_D01_DIRECTION', saved['profile']['designPrinciples'])
            published = store.publish_identity_draft('Brand', revision=2)['brand']['profile']
            text = '\n'.join(b['text'] for b in system(published))
            for banned in ('EDITED_D01_DIRECTION', 'SUPERSEDED_D01', 'REJECTED_TRIAL_DIRECTION'):
                self.assertNotIn(banned, text)
            self.assertEqual(published['identity']['cards'][0]['body'], 'EDITED_D01_DIRECTION')

    def test_asset_description_only_appears_with_the_selected_asset(self):
        profile = board()
        assets = [{'name': 'product', 'width': 100, 'height': 200}]
        text = assets_section(assets, '0.2', profile['assetNotes'])
        self.assertIn('ASSET_SEMANTIC_DESCRIPTION', text)
        self.assertNotIn('HIDDEN_ASSET_REVIEW_METADATA', text)
        self.assertNotIn('ASSET_SEMANTIC_DESCRIPTION', assets_section([], '0.2', profile['assetNotes']))

    def test_canonical_project_guidance_survives_without_reviving_stale_base(self):
        profile = identity_profile('Brand', board())
        overridden = apply_overrides(profile, {'designPrinciples': ['EXPLICIT_PROJECT_DIRECTION']})
        text = '\n'.join(b['text'] for b in system(overridden))
        self.assertIn('EXPLICIT_PROJECT_DIRECTION', text)
        self.assertNotIn('REJECTED_TRIAL_DIRECTION', text)
        stale = copy.deepcopy(overridden)
        stale['designPrinciples'][0] = 'SUPERSEDED_D01'
        stale['designPrinciples'][1] = 'REJECTED_TRIAL_DIRECTION'
        text = '\n'.join(b['text'] for b in system(stale))
        self.assertNotIn('SUPERSEDED_D01', text)
        self.assertNotIn('REJECTED_TRIAL_DIRECTION', text)

    def test_legacy_profile_principles_keep_existing_behaviour(self):
        profile = {'name': 'Old', 'swatches': [], 'fonts': [], 'designPrinciples': 'Existing approved guidance'}
        text = '\n'.join(b['text'] for b in system(profile))
        self.assertIn('Existing approved guidance', text)

    def test_working_colour_values_reject_bad_channels_and_duplicate_names(self):
        invalid = [
            {'name': 'X', 'space': 'rgb', 'values': [0, 255]},
            {'name': 'X', 'space': 'rgb', 'values': [0, 255, 256]},
            {'name': 'X', 'space': 'cmyk', 'values': [0, 1, 2]},
            {'name': 'X', 'space': 'cmyk', 'values': [0, 1, 2, 101]},
            {'name': 'X', 'space': 'cmyk', 'values': [0, 1, 2, -1]},
            {'name': 'X', 'space': 'rgb', 'values': [0, True, 2]},
            {'name': 'X', 'space': 'rgb', 'values': [0, '1', 2]},
            {'name': 'X', 'space': 'rgb', 'values': [0, float('nan'), 2]},
            {'name': 'X', 'space': 'rgb', 'values': [0, float('inf'), 2]},
            {'name': 'X', 'space': 'rgb', 'values': [0, 10**400, 2]},
            {'name': 'X', 'space': 'lab', 'values': [0, 1, 2]},
            {'name': ' ', 'space': 'rgb', 'values': [0, 1, 2]},
            None,
        ]
        for swatch in invalid:
            with self.subTest(swatch=swatch):
                profile = board()
                profile['swatches'] = [swatch]
                with self.assertRaises(ValueError):
                    identity_profile('Brand', profile)
        profile = board()
        profile['swatches'].append({**profile['swatches'][0], 'name': ' working VIOLET '})
        with self.assertRaises(ValueError):
            identity_profile('Brand', profile)

    def test_working_fonts_reject_bad_types_blank_names_and_duplicates(self):
        for fonts in (None, 'Effra Bold', [1], [True], [' '], ['Effra Bold', ' effra BOLD ']):
            with self.subTest(fonts=fonts):
                profile = board()
                profile['fonts'] = fonts
                with self.assertRaises(ValueError):
                    identity_profile('Brand', profile)

    def test_valid_definition_bounds_preserve_evidence_and_other_profile_fields(self):
        profile = board()
        profile['swatches'] = [
            {'name': 'RGB', 'space': 'rgb', 'values': [0, 127.5, 255], 'source': {'label': 'Evidence remains'}},
            {'name': 'CMYK', 'space': 'cmyk', 'values': [0, 25.5, 50, 100], 'spot': True},
        ]
        canonical = identity_profile('Brand', profile)
        self.assertEqual(canonical['swatches'], profile['swatches'])
        self.assertEqual(canonical['identity'], profile['identity'])
        self.assertEqual(canonical['charStyles'], profile['charStyles'])
        self.assertEqual(canonical['trialDecisions'], profile['trialDecisions'])
        self.assertEqual(canonical['fonts'], profile['fonts'])

    def test_invalid_saved_definition_cannot_publish_or_advance_version(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = DocStore(Path(temporary) / 'board.db')
            store.save_brand_profile('Brand', board())
            store.save_identity_draft('Brand', board(), expected_revision=0)
            invalid = board()
            invalid['swatches'][0]['values'] = [0, 0, 0, 101]
            with self.assertRaises(ValueError):
                store.save_identity_draft('Brand', invalid, expected_revision=1)
            self.assertEqual(store.get_identity_draft('Brand')['revision'], 1)
            # Represent an invalid draft saved before this validator existed.
            with store._connect() as database:
                database.execute('UPDATE identity_draft SET profile_json=? WHERE brand_name=?', (json.dumps(invalid), 'Brand'))
                database.commit()
            with self.assertRaises(ValueError):
                store.publish_identity_draft('Brand', revision=1)
            self.assertEqual(len(store.list_brand_versions('Brand')), 1)


if __name__ == '__main__':
    unittest.main()
