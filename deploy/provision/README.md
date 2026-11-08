# deploy/provision — one isolated environment per customer, as code

Terraform that creates everything one customer needs, isolated in its own GCP
project: project, VPC network and firewall, VM, storage bucket, Secret Manager
secrets (created empty — values are set on the box, never in Terraform), daily
data-disk snapshots, uptime monitoring with an email alert, and a monthly budget.

No customer exists yet, so every identity is a variable and **nothing has been
applied**: the standing state is `validate` and `plan` only. `terraform apply` is
Neil's call, with a billing account and org/folder in hand.

## Use

```bash
cd deploy/provision
/mnt/owl-data/fin-wt/ci-tools/terraform init -input=false
/mnt/owl-data/fin-wt/ci-tools/terraform plan \
  -var customer=<slug> \
  -var billing_account=XXXXXX-XXXXXX-XXXXXX \
  -var alert_email=<ops address> \
  [-var org_id=… | -var folder_id=…]
```

Sizes default to the live box's measured shape (8 Nov 2026): `e2-custom-6-32768`,
650 GB boot (live 500 GB is 94 % full), 1 TB data disk. The budget default
(USD 400/month) is an estimate, not measured; replace it once a first customer
month has real numbers.

On apply, `inventory/<customer>.json` is written (customer, region, version,
health, backup state, last deployment — "not deployed yet" until the first
release). `deploy/ci/inventory-check.sh` validates every entry.

## Isolation guarantee

Every resource targets the new `loupe-<customer>` project. The test
`deploy/tests/test-provision-isolation.sh` plans a fictional customer and fails if
the plan references the live project or targets any existing project.
