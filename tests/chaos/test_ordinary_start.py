"""Ordinary start identity tests. No native game process."""

import unittest

from chaos.ordinary_start import OPTIONS, reject_wizard_args


class OrdinaryStartTests(unittest.TestCase):
    def test_options_name_a_human_bard_with_dog(self):
        self.assertIn("role:Brd", OPTIONS)
        self.assertIn("race:human", OPTIONS)
        self.assertIn("pettype:dog", OPTIONS)
        self.assertNotIn("Wizard", OPTIONS)
        self.assertNotIn("-D", OPTIONS)

    def test_reject_wizard_mode_tokens(self):
        with self.assertRaises(ValueError):
            reject_wizard_args(["-D"])
        with self.assertRaises(ValueError):
            reject_wizard_args(["-u", "wizard"])
        with self.assertRaises(ValueError):
            reject_wizard_args(["-uwizard"])
        reject_wizard_args([])
        reject_wizard_args(["-u", "ChaosReview"])
