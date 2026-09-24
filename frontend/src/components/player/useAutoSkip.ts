import { useStoredValue } from "./useStoredValue";

/** Per-browser "skip intros/outros automatically" preference. */
export function useAutoSkip(): [boolean, (value: boolean) => void] {
  const [value, setValue] = useStoredValue<"0" | "1">("notflix:autoskip", "0");
  return [value === "1", (next) => setValue(next ? "1" : "0")];
}
