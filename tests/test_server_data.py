import gzip
import json

from grantmatch import server_data


def test_slim_keeps_what_the_score_and_page_use(tmp_path):
    samples = [{"to": f"Synthetic Org {i}", "city": "TAMPA", "state": "FL", "purpose": "Literacy", "amount": 500.0,
                "_city_title": "Tampa", "_to": f"Synthetic Org {i}"} for i in range(12)]
    payload = {"records": [{"ein": "000000001", "name": "Synthetic Fund", "sample_grants": samples}], "vec_ids": ["000000001"], "dim": 384}
    (tmp_path / "foundations-FL.json.gz").write_bytes(gzip.compress(json.dumps(payload).encode()))
    made = server_data.write_slim(tmp_path)
    assert [p.name for p in made] == ["foundations-FL.slim.json.gz"]
    slim = json.loads(gzip.decompress(made[0].read_bytes()))
    got = slim["records"][0]["sample_grants"]
    assert len(got) == 12
    assert got[:8] == samples[:8]
    assert got[8] == {"city": "TAMPA", "state": "FL", "purpose": "Literacy", "_city_title": "Tampa"}
    assert slim["vec_ids"] == ["000000001"]
    # running it again leaves the slim copy alone instead of slimming it twice
    assert [p.name for p in server_data.write_slim(tmp_path)] == ["foundations-FL.slim.json.gz"]


def test_only_small_public_files_go_to_the_site(tmp_path):
    for name in ["meta.json", "examples.json", "coverage.json", "changes.json", "counties-FL.json",
                 "federal.json.gz", "federal.f16", "foundations-FL.json.gz", "florida.json.gz"]:
        (tmp_path / name).write_text("{}")
    site = tmp_path / "site"
    assert server_data.copy_public(tmp_path, site) == ["changes.json", "counties-FL.json", "coverage.json", "examples.json", "meta.json"]
    assert not (site / "federal.json.gz").exists()


class FakeHttp:
    def __init__(self):
        self.puts = []

    def post(self, url, json, headers, timeout):
        assert headers["x-ingest-token"] == "synthetic-token"
        return FakeRes({"links": {n: f"https://gm.test/up/{n}" for n in json["names"]}})

    def put(self, url, data, headers, timeout):
        self.puts.append(url)
        return FakeRes({})


class FakeRes:
    ok = True
    status_code = 200

    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self.body


def test_upload_sends_every_data_file_and_nothing_else(tmp_path):
    for name in ["meta.json", "federal.json.gz", "federal.f16", "foundations-CA.slim.json.gz", "notes.txt", ".hidden.json"]:
        (tmp_path / name).write_text("{}")
    http = FakeHttp()
    assert server_data.upload(tmp_path, "https://gm.test/ingest", "synthetic-token", http) == 4
    assert sorted(u.rsplit("/", 1)[1] for u in http.puts) == ["federal.f16", "federal.json.gz", "foundations-CA.slim.json.gz", "meta.json"]
