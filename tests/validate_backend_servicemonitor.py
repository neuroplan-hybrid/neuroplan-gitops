"""Compare rendered objects. No cluster calls or credentials are used."""
import sys
import yaml

def load(path):
    with open(path, encoding="utf-8") as stream:
        docs = [x for x in yaml.safe_load_all(stream) if x]
    result = {}
    for obj in docs:
        meta = obj["metadata"]
        key = (obj["apiVersion"], obj["kind"], meta.get("namespace", ""), meta["name"])
        assert key not in result, f"Duplicate identity: {key}"
        result[key] = obj
    return result

def validate(before, after, onprem_before, onprem_after):
    monitor_key = ("monitoring.coreos.com/v1", "ServiceMonitor", "neuroplan", "neuroplan-backend")
    expected_added = set() if monitor_key in before else {monitor_key}
    assert set(after) - set(before) == expected_added, "Only the ROSA ServiceMonitor may be added"
    assert not set(before) - set(after), "Existing objects must not be deleted"
    for key, obj in before.items():
        if key != monitor_key:
            assert after[key] == obj, f"Unexpected existing object change: {key}"
    assert onprem_before == onprem_after, "onprem-dr must remain identical"
    monitor = after[monitor_key]
    assert set(monitor["spec"]) == {"selector", "endpoints"}, "No cross-namespace or extra spec options"
    selector = monitor["spec"]["selector"]["matchLabels"]
    assert monitor["spec"]["selector"]["matchExpressions"] == [{"key": "neuroplan.io/purpose", "operator": "DoesNotExist"}]
    matches = [obj for obj in after.values() if obj["kind"] == "Service"
               and obj["metadata"].get("namespace") == "neuroplan"
               and all(obj["metadata"].get("labels", {}).get(k) == v for k, v in selector.items())
               and "neuroplan.io/purpose" not in obj["metadata"].get("labels", {})]
    assert len(matches) == 1 and matches[0]["metadata"]["name"] == "neuroplan-backend", "Select only Backend Service"
    endpoint = monitor["spec"]["endpoints"]
    assert endpoint == [{"port": "http", "path": "/actuator/prometheus", "scheme": "http",
                         "interval": "30s", "scrapeTimeout": "10s"}]
    ports = [p for p in matches[0]["spec"]["ports"] if p["name"] == "http"]
    assert len(ports) == 1 and ports[0]["port"] == 8080 and ports[0]["targetPort"] == "http"
    deploy = after[("apps/v1", "Deployment", "neuroplan", "neuroplan-backend")]
    assert any(p["name"] == "http" and p["containerPort"] == 8080
               for c in deploy["spec"]["template"]["spec"]["containers"] for p in c.get("ports", []))
    print("PASS: only ROSA Backend ServiceMonitor added; existing ROSA/onprem objects unchanged; Service selector and named port validated")

if __name__ == "__main__":
    assert len(sys.argv) == 5, "Supply baseline ROSA, changed ROSA, baseline onprem, changed onprem YAML"
    validate(*(load(path) for path in sys.argv[1:]))
