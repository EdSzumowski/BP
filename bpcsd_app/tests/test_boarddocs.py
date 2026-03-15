import unittest

from modules.boarddocs import BoardDocsClient


class BoardDocsParsingTests(unittest.TestCase):
    def test_all_agenda_items_supports_shorter_ids_and_data_id(self):
        client = BoardDocsClient.__new__(BoardDocsClient)
        html = '''
        <div id="ABCD123456" Xtitle="Communications BOE Report Feb 2025"></div>
        <div data-id="XYZ9876543" data-title="Special Education BOE Report Feb 2025"></div>
        '''
        items = client._all_agenda_items(html)

        self.assertIn(("ABCD123456", "Communications BOE Report Feb 2025"), items)
        self.assertIn(("XYZ9876543", "Special Education BOE Report Feb 2025"), items)


if __name__ == "__main__":
    unittest.main()
