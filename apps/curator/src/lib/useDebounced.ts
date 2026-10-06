import { useEffect, useState } from "react";

/**
 * Holds a value still until it stops changing.
 *
 * A search box wired straight into a server-side query fires one request per keystroke, and the
 * archivist types the whole word before reading the answer: the intermediate requests are paid for and
 * thrown away. The delay is the same 250 ms the collection search uses, so the two boxes feel alike.
 *
 * This is a *delay*, not a throttle or a cache: the last value always arrives.
 */
export function useDebounced<T>(value: T, delay = 250): T {
  const [settled, setSettled] = useState(value);

  useEffect(() => {
    const handle = setTimeout(() => setSettled(value), delay);
    return () => clearTimeout(handle);
  }, [value, delay]);

  return settled;
}
