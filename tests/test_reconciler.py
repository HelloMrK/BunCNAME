import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from reconciler import Reconciler
from tests.fake_provider import FakeProvider


def entry(domain, providers, records):
    return {"domain": domain, "providers": providers, "records": records}


def rec(host, content, rtype="CNAME", ttl=600):
    return {"host": host, "type": rtype, "content": content, "ttl": ttl}


def make(provider):
    return Reconciler({"fake": provider}, managed_types={"CNAME"})


def test_creates_missing_records():
    p = FakeProvider()
    s = make(p).sync_config([entry("example.com", "fake", [rec("www", "target.io")])])
    assert p.store[("www", "CNAME")]["content"] == "target.io"
    assert s["results"][0]["created"] == 1 and not s["errors"]


def test_updates_changed_content_and_ttl():
    p = FakeProvider([{"host": "www", "content": "old.io", "ttl": 300}])
    s = make(p).sync_config([entry("example.com", "fake", [rec("www", "new.io", ttl=600)])])
    assert p.store[("www", "CNAME")]["content"] == "new.io"
    assert p.store[("www", "CNAME")]["ttl"] == 600
    assert s["results"][0]["updated"] == 1 and not s["errors"]


def test_noop_when_in_sync():
    p = FakeProvider([{"host": "www", "content": "target.io", "ttl": 600}])
    s = make(p).sync_config([entry("example.com", "fake", [rec("www", "target.io")])])
    assert s["results"][0]["created"] == 0 and s["results"][0]["updated"] == 0
    assert s["results"][0]["deleted"] == 0 and not s["errors"]


def test_deletes_records_missing_from_desired():
    p = FakeProvider([
        {"host": "keep", "content": "a.io"},
        {"host": "drop", "content": "b.io"},
    ])
    s = make(p).sync_config([entry("example.com", "fake", [rec("keep", "a.io")])])
    assert ("drop", "CNAME") not in p.store
    assert ("keep", "CNAME") in p.store
    assert s["results"][0]["deleted"] == 1 and not s["errors"]


def test_unmanaged_types_untouched():
    """A/MX records on remote must NOT be deleted even if absent from desired."""
    p = FakeProvider([
        {"host": "root", "content": "1.2.3.4", "type": "A"},
        {"host": "mx", "content": "mail.io", "type": "MX"},
    ])
    s = make(p).sync_config([entry("example.com", "fake", [rec("www", "t.io")])])
    assert ("root", "A") in p.store and ("mx", "MX") in p.store
    assert not s["errors"]


def test_managed_types_can_include_a():
    p = FakeProvider([{"host": "", "content": "1.2.3.4", "type": "A"}])
    r = Reconciler({"fake": p}, managed_types={"CNAME", "A"})
    s = r.sync_config([
        entry("example.com", "fake", [
            rec("", "9.9.9.9", rtype="A"),
            rec("www", "t.io"),
        ]),
    ])
    assert p.store[("", "A")]["content"] == "9.9.9.9"
    assert ("www", "CNAME") in p.store
    assert s["results"][0]["updated"] == 1 and s["results"][0]["created"] == 1


def test_providers_string_backward_compat():
    p = FakeProvider()
    make(p).sync_config([entry("example.com", "fake", [rec("www", "t.io")])])
    assert ("www", "CNAME") in p.store


def test_unknown_provider_reports_error():
    s = make(FakeProvider()).sync_config([entry("example.com", "nope", [rec("www", "t.io")])])
    assert s["errors"], "unknown provider must surface as summary error"


def test_partial_failure_reports_errors():
    p = FakeProvider(fail_on="delete_record")
    p._seed({"host": "drop", "content": "b.io"})
    s = make(p).sync_config([entry("example.com", "fake", [rec("keep", "a.io")])])
    assert s["errors"], "failed delete must surface in summary errors"
    assert ("keep", "CNAME") in p.store  # create still attempted


def test_fetch_failure_reports_error():
    p = FakeProvider(fail_on="get_records")
    s = make(p).sync_config([entry("example.com", "fake", [rec("www", "t.io")])])
    assert s["errors"] and "failed to fetch" in s["errors"][0]


def test_apex_host_handled():
    p = FakeProvider([{"host": "", "content": "root.io"}])
    s = make(p).sync_config([entry("example.com", "fake", [rec("", "new-root.io")])])
    assert p.store[("", "CNAME")]["content"] == "new-root.io"
    assert s["results"][0]["updated"] == 1 and not s["errors"]
