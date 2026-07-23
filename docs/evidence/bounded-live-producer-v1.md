# Bounded Live Producer Evaluation v1

Status: valid bounded producer observation.

## Source Receipt

- Repository: `decision-research-agent`
- Version: `0.1.5`
- Source commit: `eb2be018cc97e7133b850a001521e292b752c9cd`
- Source tree: `a34ad60ce516ade5f70deac5ff2b21803eca6764`
- Tracked archive SHA-256: `66fd738794bb8efe7c7483f92587f635660dd671b5b529ae59e565f8be3b41b5`
- Manifest SHA-256: `3d4f9aeaea30607eb8b1107862f346be42ff73b77830ab087d8c4e70dcb5cfe7`
- Build context: `tracked_archive`

## Scenario And Result

- Scenario: `cpython-313-free-threaded-pilot`
- Run: `run_e6efb8d7b9794aa6be32fefa9dc179fd`
- Artifact: `research-report.md` (`947b7bc5f46c980a8b68867b6e66c6436b2012cfbb9b720b1e626da3a6bd65a5`)
- Consumer projection: `supported / accept_draft`

## Evidence

- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_e5be36e5441f40ec1f268b492ee3c7d45758bc845c392c096da97f47c1c4c1f6` — https://docs.python.org/3/howto/free-threading-python.html — `cited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_67d4c697d22c4a5cac2543d69ba2fc74d7e7e55af753db3f697b14a5033bf9dc` — https://dev.to/zackch/python-313-no-gil-what-you-need-to-know-352i — `uncited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_2c1595ff905ca65cf5ed9396c8bf6113795876964ae7205ab77d495a7c0d1fed` — https://docs.python.org/3/whatsnew/3.13.html — `cited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_9d5327fcc0f4710e94fb345824f29779a24597ab0e79f7adf3662d37d7a59fdc` — https://medium.com/@mitesh.singh.jat/gil-becomes-optional-in-python-3-13-a-game-changer-for-multithreading-4c5d28856803 — `uncited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_19d84ba332ecb9437a8e1a638dfe3de1400d7da503c1ea5d7d54ee6273cc2e18` — https://blog.jetbrains.com/pycharm/2025/07/faster-python-unlocking-the-python-global-interpreter-lock — `uncited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_bd9d0281e400ad2098a840a9158972357d77d88dc1d1c739a500a030eec7eaf3` — https://flyaps.com/blog/update-python-3-13 — `uncited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_167bdcf94c1e613abecb1fb9001ef83808e3a1a35bcd6db6b4053a3924dba552` — https://www.reddit.com/r/programming/comments/1eq4vzd/gil_become_optional_in_python_313 — `uncited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_09c08655bacf424df4ce01c1dd12057ab1a203f32cc10f33d7c369c1f2910ade` — https://docs.python.org/zh-tw/3.13/howto/free-threading-python.html — `uncited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_1b6d931395a87eb478b2878b68689ac9689a60e68f87dca9880206ec40d1b283` — https://docs.python.org/zh-cn/dev/howto/free-threading-python.html — `cited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_00d9ff73ffae321bdf78bccf7e74c99eea18288772c541ecd4ac1493ea5f25ea` — https://docs.python.org/3/howto/free-threading-extensions.html — `cited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_0d858b8cf42e74b13f6125a013c2c46135b9bc7efdf4f1dcec26be870f2e9ff5` — https://docs.python.org/3/c-api/threads.html — `uncited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_ac6b2c57c037046fe018b3efb131d970971e96be26522f0bc9820413fef43324` — https://docs.python.org/3/library/threadsafety.html — `cited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_4873b4088551eecbf5833f1f828d53142238897e5850eff1feb8f580ffb69a82` — https://docs.python.org/3.13/c-api/init.html — `uncited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_2003feee3cef8e44a3de3452bdbaa8918f324a0464c4bb89cf9a93a2a22782f1` — https://docs.python.org/3/library/threading.html — `uncited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_068c23a213bb92bfe1e3571089cc36b132435bbc57c5cb68ab9fe1ad0d27753f` — https://docs.python.org/3/whatsnew/3.14.html — `uncited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_a3b200b90bc7482a0f986b817a8d8623598a8bf49b975a5a0eab63bd09b07572` — https://peps.python.org/pep-0703 — `cited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_76c2f99178d6eae1643c7c255efcd127bc5596d3a11256c9ef0715b4fc8b8aad` — https://peps.python.org/pep-0809 — `uncited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_ced9379eaee0590c59d4c61fc1f114ef14f5dec40f004661519e0de2bd4f02c2` — https://peps.python.org/pep-0803 — `cited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_1a197b38db0914121326d718cf170682f73dadef201bd3dbe9eff3f2d256766f` — https://peps.python.org/pep-0780 — `cited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_87e797feece545044969af6f18d3846eb98bf1647bd20b3f44c46654a621d648` — https://peps.python.org — `uncited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_befc880679c9cb89ec66618f5021168d2d966188a548fab5663f054509fa6b75` — https://lwn.net/Articles/919563 — `uncited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_92c14ace2a567319ec8bca3ef9fd3640f3b5aa766191fa9b0651ace350cd59a8` — https://pydevtools.com/handbook/explanation/what-is-pep-703 — `uncited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_c57d2ed49fa413d690c749e3418c450c4b19ae36b9043e25cf33b86afd8dcbc6` — https://discuss.python.org/t/pep-703-making-the-global-interpreter-lock-optional-in-cpython-acceptance/37075 — `cited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_25f6a9fb758b9e02b3182d975765def075d93936a6b12ba22bb47abb925f384d` — https://www.reddit.com/r/Python/comments/14534lk/pep_703_making_the_global_interpreter_lock — `uncited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_b5d48097d31688aa30f3d9a05c093fa19537616f14e1437d97af047e0f4c03b5` — https://peps.python.org/pep-0779 — `cited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_5f3da9b5bcab403a4644930a93481359508c7249301ab116f49c0c71673fc829` — https://peps.python.org/pep-0780 — `cited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_e61c98d42a39aaf80cd9788cc63b0124c9a749c2e77a3ad004af5ba8276551dd` — https://peps.python.org/pep-0814 — `uncited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_45f1dec3106d809569cf298fc0741a1e151247885c18dea5b83745f52e65339e` — https://peps.python.org/pep-0836 — `cited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_e493cb2527e07de57ec74984fb9f23f3065fb07146c590dfca35dc879eede15f` — https://peps.python.org/pep-0703 — `cited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_e74fedecdc8c868f158eceb111183f5b918ba5ab21a2119531229848d11fedb9` — https://docs.python.org/pt-br/3.13/howto/free-threading-python.html — `uncited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_3035e475be45994166039bf20c7ac791e529eb9333b12add9c776d0df8441036` — https://docs.python.org/es/3.13/howto/free-threading-python.html — `uncited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_9a73eb539799bcf3cacd9382fd0f64b86016f140d02c355e892d05516c3b8146` — https://docs.python.org/zh-cn/3.13/howto/free-threading-python.html — `cited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_b663dba93920739e21cb0aedb919a9aad71b4bd4a676ef40040e3dc46d1b0f0e` — https://docs.python.org/pt-br/3/howto/free-threading-python.html — `uncited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_03395df2bd9f7b07ac2dff9ac09bb8026d504b52275727079ba64aa88d375b83` — https://github.com/PyO3/maturin/issues/3064 — `uncited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_9fb1c20a0666369a716735cff8894b585e17fb2ac53a090ad255aacc64387da2` — https://github.com/python/steering-council/issues/333 — `uncited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_efa6449d927712a267a2b22d796c4dcf5fb50818d66ed372ef25829e9a903fcc` — https://discuss.python.org/t/pep-803-stable-abi-for-free-threaded-builds/103628 — `uncited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_94a5b022e596f9699c2ada911c509aaec3755fd45fe8e2764fa6332f4d32e4cb` — https://github.com/capi-workgroup/decisions/issues/98 — `uncited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_268fa0625f75c41e339cfca18f56b398bdb45dbbc79a495ef2b8525a20d86ab5` — https://peps.python.org/pep-0779 — `cited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_d1424eafbc8e8671f8e26273237d6184c8c6717a97260b4fa5fcdb5af25c8816` — https://py-free-threading.github.io — `cited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_de7aed1e0b5acf9bad93ce757475571b00ca17b4784a5a3d596219be731d2fb8` — https://tomaszs2.medium.com/python-is-going-free-threaded-the-end-of-the-gil-is-near-in-python-3-14-5f835ba5466f — `uncited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_4320e223c4dba17763ea79f9dea4df0c6194ba58ec3402bbec3e48782ca55437` — https://discuss.python.org/t/pep-779-criteria-for-supported-status-for-free-threaded-python/84319 — `uncited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_a756c4d004d6e12ed4e24378919c635acf8284bb638e48aadcbc286a996a26e7` — https://www.facebook.com/LearnRealPython/posts/pep-779-criteria-for-supported-status-for-free-threaded-python-python/970948348586882 — `uncited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_60b66de720c1bc5d8bf5033b6f44e53d49f8ee917709f6548124c03a3e557af8` — https://docs.python.org/3/_sources/using/configure.rst.txt — `uncited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_0bf06fe57959d234cb445f4ec8e1accdda00ec14197b26bfc44a76ccc66ed888` — https://docs.python.org/3/using/configure.html — `cited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_959905666126d0a31452f90f464e32f1f8cb59a7d748f06bfc16111048dbd2ca` — https://docs.python.org/zh-tw/3.13/using/configure.html — `uncited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_461c5a32229cb8f405dc6532554dd2ec4ffcdddd717180703fa77d41a3bf93b7` — https://docs.python.org/3/glossary.html — `uncited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_1425f11b1ec902f08b30b62a9c087631849293c363001acb63265da805a63180` — https://docs.python.org/es/3.13/howto/free-threading-python.html — `uncited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_f485cff63e8a8d0d085f106a6cceeb71ee82af7df9aceb0dc1535f1db91551c3` — https://docs.python.org/3/howto/free-threading-python.html — `cited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_e8f182156a624dc0a0e5c0ae1c9794a1c927243885bc535cccf269d7d9e283a6` — https://docs.python.org/3/whatsnew/3.13.html — `cited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_49e93099d8883a5f68287c832c4e927b57d3c39c8ea71ef5da66fdc48c5522e1` — https://docs.python.org/3/whatsnew/3.14.html — `uncited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_71e1180c041c2f285b2443f8ce3734afbc1edafb009cc027164e744c4325c399` — https://docs.python.org/3.13/whatsnew/changelog.html — `uncited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_91a7ac5046dde0d0701c24e409c279dd3ae1fa3aa3b1fd809c4ab739f2d9a904` — https://docs.python.org/3/c-api/memory.html — `cited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_88a0dbec103e296a4f221834682a6e0e94985bcee3ea4fc803ccfe46152dd8d5` — https://docs.python.org/ja/3/reference/datamodel.html — `uncited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_799f35e35c895a092fc7ae0cc7e08df42e9ddc0eb24e0ed153e377984c394994` — https://docs.python.org/uk/3/reference/datamodel.html — `uncited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_3c2bc0dcee8b59abff94ecf90f2c36dc5156048ef19f221e6307a57534c1ab88` — https://docs.python.org/ko/3.15/reference/datamodel.html — `uncited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_32df35fd68efd197f1e2fe41a1e1e73a1276654888e1bcb0449eb52af596a5eb` — https://docs.python.org/fr/3/reference/datamodel.html — `uncited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_37506ab8513904b98341a6abb613377e06cf3139c5fe03176fc2edb1c421b135` — https://docs.python.org/3/reference/datamodel.html — `uncited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_f64b2b7ac3ae79c168c6480e02c208c86b43c410730c67e8bf39c639f09b7f3f` — https://docs.python.org/3/library/concurrent.futures.html — `uncited` / `unverified`
- `ev_run_e6efb8d7b9794aa6be32fefa9dc179fd_288b4cc95ab1370d17f1a87e2dbe7abb900a59d24bbd955d8a3b04f0bddf3fe0` — https://docs.python.org/3.15/whatsnew/3.15.html — `uncited` / `unverified`

## Boundaries

- `producer_observation: bounded`
- `downstream_business_acceptance: not_claimed`
- `source_truth_or_independent_verification: not_claimed`
- `exactly_once_execution_or_provider_side_effects: not_claimed`
- `running_execution_recovery: not_claimed`
- `multi_instance_high_availability: not_claimed`
- `durable_usage_or_provider_billing: not_claimed`
- `hosted_production_or_sla: not_claimed`

## Limits

- A valid report is one bounded producer observation, not a downstream business decision.
- Recorded or cited Evidence is not independently verified source truth.
- Idempotent create reconciliation does not prove exactly-once execution or provider side effects.
- Client observation timeout does not cancel or recover a running server execution.
- Token and cost observations are process-local estimates, not durable usage or provider billing.
- The loopback Compose proof is not hosted production, multi-instance availability, or an SLA.
