# Phone journey tests (live, signed in, over http)

Scripted browser tests of the phone journeys (07 sections 3, 10.1 and 11). They run against the live address in a
real browser, signed in once with the jobs login, on the synthetic cases only (phones-only and training); they
refuse to open any other case. Output is one line per journey: passed, or the step that failed, with time and
actions. No page text, no screenshots of real cases, and the password is never printed.

    cd frontend_v2
    nice -n 15 ionice -c3 flock /mnt/owl-data/fin-wt/suite.lock node journeys/run.mjs --owner cb-screens

Each file in `specs/` belongs to the job that owns those screens (07 section 11). The tests were written first
and are red until the screens exist; the owning job turns them green as it builds, and may sharpen a selector to
match its final markup as long as the journey, its wording checks and its targets stay as written.
