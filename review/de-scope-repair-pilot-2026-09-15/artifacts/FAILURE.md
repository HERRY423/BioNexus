# Attempt 01 setup failure

The first frozen run stopped while serializing the first audit result because a
NumPy `int64` value was not JSON serializable. No case result or summary was
completed. The partial source snapshot and identity file are retained here.

The runner was updated to serialize scalar values through their native `item()`
representation. The corrected run uses a new `attempt-02` directory and refuses
to overwrite either attempt.
