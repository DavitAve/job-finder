import json

from job_finder.adapters.staffam import extract_staff_am_jobs


def test_extracts_company_jobs_from_next_data_and_ignores_other_companies() -> None:
    payload = {
        "props": {
            "pageProps": {
                "activeJobs": [
                    {
                        "id": 161914,
                        "title": {"en": "Senior React JS Engineer"},
                        "slug": {"en": "senior-react-js-engineer-10"},
                        "category": {"code": "software-development"},
                        "companiesStruct": {"title": {"en": "SoftConstruct"}},
                        "job_city": {"title": {"en": "Yerevan"}},
                        "activated_at": {"staffam": "2026-07-31 10:37:05"},
                    },
                    {
                        "id": 2,
                        "title": {"en": "Vue Engineer"},
                        "slug": {"en": "vue-engineer"},
                        "category": {"code": "software-development"},
                        "companiesStruct": {"title": {"en": "Another Company"}},
                    },
                ]
            }
        }
    }
    html = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(payload)}</script>'
    jobs = extract_staff_am_jobs(
        html, "https://staff.am/company/softconstruct", "SoftConstruct"
    )
    assert len(jobs) == 1
    assert jobs[0].title == "Senior React JS Engineer"
    assert jobs[0].location == "Yerevan"
    assert jobs[0].source_job_id == "161914"
    assert jobs[0].url == (
        "https://staff.am/jobs/software-development/senior-react-js-engineer-10"
    )
