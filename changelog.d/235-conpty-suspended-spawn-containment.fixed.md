- **ConPTY containment: the job-assignment window is closed.** The binding
  now creates its child with `CREATE_SUSPENDED`, assigns it to the
  kill-on-close job while still suspended, and only then resumes the main
  thread — no descendant can predate the job membership, so containment is
  a property of the spawn rather than a near-certainty. Every failure path
  between creation and resume terminates the suspended child (a suspended
  process cannot die of handle closes) and closes the thread handle. New
  Windows-matrix evidence: creation flags plus assign-before-resume call
  order, containment failure provably never resumes, and a fault-injected
  post-creation failure leaves no suspended orphan. The disclosed boundary
  is deleted from the module, and the architecture knowledge page and
  boundary-hardening handover record the closure. The JSONL transport's
  Windows spawn does not own `CreateProcess` and retains the window — a
  separate, disclosed boundary. (Closes #235.)
