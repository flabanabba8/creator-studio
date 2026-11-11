import unittest
from unittest.mock import patch
from test_tutorial import package

core = package.core
WINDOW = 'Window id: 0x2 "Notes"\nWidth: 400\nHeight: 300\nAbsolute upper-left X: 20\nAbsolute upper-left Y: 30\nMap State: IsViewable\n'
ROOT = 'Window id: 0x1 (the root window)\nWidth: 800\nHeight: 600\n'


class WindowRegion(unittest.TestCase):
    def test_region_is_bounded_to_selected_window_and_includes_pointer(self):
        with patch.object(core, 'run', side_effect=[WINDOW, ROOT]):
            source = core.window_info(':7', '0x2', 'window_region')
        command = core.capture_input({**source, 'capture_mode': 'window_region', 'show_cursor': True})
        self.assertEqual(source['left'], 20)
        self.assertEqual(source['top'], 30)
        self.assertEqual(command[command.index('-video_size') + 1], '400x300')
        self.assertEqual(command[command.index('-draw_mouse') + 1], '1')
        self.assertEqual(command[-2:], ['-i', ':7+20,30'])
        self.assertNotIn('-window_id', command)

    def test_existing_request_keeps_window_capture_and_hidden_pointer(self):
        with patch.object(core, 'run', side_effect=[WINDOW, ROOT]):
            source = core.window_info(':7', '0x2')
        self.assertNotIn('left', source)
        command = core.capture_input(source)
        self.assertEqual(command[-4:], ['-window_id', '2', '-i', ':7'])
        self.assertEqual(command[command.index('-draw_mouse') + 1], '0')

    def test_region_cannot_be_root_or_partly_off_screen(self):
        with patch.object(core, 'run', side_effect=[WINDOW, ROOT]):
            with self.assertRaisesRegex(ValueError, 'Desktop/root'):
                core.window_info(':7', '0x1', 'window_region')
        for changed in [WINDOW.replace('X: 20', 'X: -1'), WINDOW.replace('X: 20', 'X: 500')]:
            with patch.object(core, 'run', side_effect=[changed, ROOT]):
                with self.assertRaisesRegex(ValueError, 'fully on screen'):
                    core.window_info(':7', '0x2', 'window_region')

    def test_invalid_mode_or_unvalidated_region_is_refused(self):
        with self.assertRaises(ValueError):
            core.window_info(':7', '0x2', 'desktop')
        request = {'display': ':7', 'window_id': 2, 'width': 400, 'height': 300,
                   'capture_mode': 'window_region', 'left': -1, 'top': 0}
        with self.assertRaises(ValueError): core.capture_input(request)
        with self.assertRaises(ValueError): core.capture_input({**request, 'show_cursor': 'yes'})
