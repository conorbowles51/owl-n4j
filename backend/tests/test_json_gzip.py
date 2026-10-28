import gzip
import json
import unittest

from fastapi import FastAPI
import tempfile

from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.testclient import TestClient

from services.json_gzip import JSONGZipMiddleware

PAYLOAD = {'rows': [{'id': index, 'description': 'PAYMENT TO SUPPLIER ' * 3} for index in range(500)]}
ARCHIVE = bytes(range(256)) * 200
LARGE = {'rows': [{'id': index, 'description': 'PAYMENT TO SUPPLIER %d' % index} for index in range(20000)]}
JSON_FILE = tempfile.NamedTemporaryFile(suffix='.json', delete=False)
JSON_FILE.write(json.dumps(PAYLOAD).encode()); JSON_FILE.close()


def app():
    application = FastAPI()
    application.add_middleware(JSONGZipMiddleware)

    @application.get('/json')
    def as_json():
        return PAYLOAD

    @application.get('/small')
    def small():
        return {'ok': True}

    @application.get('/zip')
    def archive():
        return Response(content=ARCHIVE, media_type='application/zip')

    @application.get('/stream')
    def stream():
        return StreamingResponse(iter([b'data: one\n\n', b'data: two\n\n']), media_type='text/event-stream')

    @application.get('/encoded')
    def encoded():
        return JSONResponse(content=PAYLOAD, headers={'Content-Encoding': 'identity'})

    @application.get('/large')
    def large():
        return LARGE

    @application.get('/json-file')
    def json_file():
        return FileResponse(JSON_FILE.name, media_type='application/json')

    @application.get('/json-attachment')
    def json_attachment():
        return JSONResponse(content=PAYLOAD, headers={'Content-Disposition': 'attachment; filename="rows.json"'})

    return application


class JSONGZipTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app())

    def raw(self, path, encoding='gzip'):
        response = self.client.get(path, headers={'Accept-Encoding': encoding})
        return response

    def test_json_is_gzipped_and_decodes_to_the_same_bytes(self):
        plain = self.client.get('/json', headers={'Accept-Encoding': 'identity'})
        self.assertNotIn('content-encoding', plain.headers)
        with self.client.stream('GET', '/json', headers={'Accept-Encoding': 'gzip'}) as response:
            self.assertEqual(response.headers['content-encoding'], 'gzip')
            wire = b''.join(response.iter_raw())
        self.assertLess(len(wire), len(plain.content) / 5)
        self.assertEqual(gzip.decompress(wire), plain.content)
        self.assertEqual(json.loads(plain.content), PAYLOAD)

    def test_downloads_streams_small_and_encoded_responses_pass_through(self):
        for path in ('/zip', '/stream', '/small', '/encoded'):
            with self.subTest(path=path), self.client.stream('GET', path, headers={'Accept-Encoding': 'gzip'}) as response:
                self.assertNotEqual(response.headers.get('content-encoding'), 'gzip')
                wire = b''.join(response.iter_raw())
            if path == '/zip':
                self.assertEqual(wire, ARCHIVE)
            if path == '/stream':
                self.assertEqual(wire, b'data: one\n\ndata: two\n\n')

    def test_large_json_is_compressed_off_the_loop_with_exact_length(self):
        plain = self.client.get('/large', headers={'Accept-Encoding': 'identity'})
        self.assertGreater(len(plain.content), 256 * 1024)
        with self.client.stream('GET', '/large', headers={'Accept-Encoding': 'gzip'}) as response:
            self.assertEqual(response.headers['content-encoding'], 'gzip')
            self.assertIn('Accept-Encoding', response.headers['vary'])
            wire = b''.join(response.iter_raw())
        self.assertEqual(int(response.headers['content-length']), len(wire))
        self.assertEqual(gzip.decompress(wire), plain.content)

    def test_json_files_attachments_and_ranges_are_sent_unchanged(self):
        original = open(JSON_FILE.name, 'rb').read()
        for path, extra in (('/json-file', {}), ('/json-file', {'Range': 'bytes=0-99'}), ('/json-attachment', {})):
            with self.subTest(path=path, extra=extra), self.client.stream('GET', path, headers={'Accept-Encoding': 'gzip', **extra}) as response:
                self.assertNotEqual(response.headers.get('content-encoding'), 'gzip')
                wire = b''.join(response.iter_raw())
            if path == '/json-file':
                self.assertEqual(wire, original[:100] if extra else original)
                self.assertEqual(response.status_code, 206 if extra else 200)


if __name__ == '__main__':
    unittest.main()
