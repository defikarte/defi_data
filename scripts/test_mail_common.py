"""
Tests für mail_common: Umrechnung WGS84 -> LV95 mit dem Prüfpunkt von
swisstopo und Kontaktzeile der Karten.

Verwendung:
    python3 scripts/test_mail_common.py
"""

import unittest

import mail_common
from mail_common import contact_html, contact_info, coords_html, truncate, wgs84_to_lv95


class Wgs84ToLv95(unittest.TestCase):
    def test_swisstopo_pruefpunkt(self):
        # 46°02'38.87" N / 8°43'49.79" E
        e, n = wgs84_to_lv95(46.044130556, 8.730497222)
        self.assertLess(abs(e - 2699999.76), 1)
        self.assertLess(abs(n - 1099999.97), 1)


class CoordsLine(unittest.TestCase):
    def tearDown(self):
        mail_common.COORDS_MODE = "none"

    def line(self, mode):
        mail_common.COORDS_MODE = mode
        return coords_html({"status": "Neu", "lat": 46.044130556, "lon": 8.730497222})

    def test_formate(self):
        self.assertIn(">46.044131, 8.730497</div>", self.line("wgs84"))
        self.assertIn(">LV95 2700000, 1100000</div>", self.line("lv95"))
        self.assertIn(">46.044131, 8.730497 · LV95 2700000, 1100000</div>", self.line("both"))
        self.assertEqual(self.line("none"), "")


class Contact(unittest.TestCase):
    def setUp(self):
        mail_common.SHOW_CONTACT = True

    def tearDown(self):
        mail_common.SHOW_CONTACT = False

    def line(self, status="Neu", **tags):
        return contact_html({"status": status, "contact": contact_info(tags)})

    def test_fallback_reihenfolge(self):
        self.assertEqual(contact_info({"operator:name": "B", "contact:mobile": "3", "contact:phone": "2",
                                       "contact:email": "b@x.ch", "operator:email": "c@x.ch"}),
                         {"operator": "B", "phone": "2", "email": "b@x.ch"})
        self.assertEqual(contact_info({"phone": " ", "contact:phone": "2"}), {"phone": "2"})

    def test_keine_angaben_keine_zeile(self):
        self.assertEqual(self.line(**{"emergency:phone": "144"}), "")
        self.assertEqual(self.line(operator="  "), "")

    def test_nur_neu_und_geaendert(self):
        self.assertIn(">A</div>", self.line("Geändert", operator="A"))
        self.assertEqual(self.line("Gelöscht", operator="A"), "")

    def test_ohne_kundenwunsch_leer(self):
        mail_common.SHOW_CONTACT = False
        self.assertEqual(self.line(operator="A"), "")

    def test_trenner_ohne_labels(self):
        line = self.line(operator="A", phone="1", email="b@x.ch")
        self.assertIn('>A · <a href="tel:1"', line)
        self.assertIn('>1</a> · <a href="mailto:b@x.ch"', line)

    def test_betreiber_nicht_doppelt(self):
        def line(name, operator):
            return contact_html({"status": "Neu", "name": name, "contact": contact_info({"operator": operator, "phone": "1"})})
        self.assertNotIn("Gemeinde A", line("Gemeinde A", "Gemeinde A"))
        self.assertIn("Gemeinde A", line("Turnhalle", "Gemeinde A"))
        long_name = "B" * 90
        self.assertIn(long_name, line(truncate(long_name, 80), long_name))

    def test_links(self):
        line = self.line(phone="+41 81 423 36 00;+41814233680", email="a@x.ch?bcc=b@x.ch")
        self.assertIn('href="tel:+41814233600"', line)
        self.assertIn('href="tel:+41814233680"', line)
        self.assertIn('href="mailto:a@x.ch%3Fbcc%3Db@x.ch"', line)

    def test_escaping(self):
        line = self.line(operator='<b>A&B</b>', email='"><script>@x.ch')
        self.assertIn("&lt;b&gt;A&amp;B&lt;/b&gt;", line)
        self.assertNotIn("<script>", line)
        self.assertNotIn("<b>", line)


if __name__ == "__main__":
    unittest.main()
