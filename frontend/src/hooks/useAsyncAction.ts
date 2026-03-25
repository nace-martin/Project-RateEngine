"use client";

import { useCallback, useRef, useState } from "react";

type AsyncActionOptions<TResult> = {
  onSuccess?: (result: TResult) => void | Promise<void>;
  onError?: (error: Error) => void | Promise<void>;
};

export function useAsyncAction<TArgs extends unknown[], TResult>(
  action: (...args: TArgs) => Promise<TResult>,
  options?: AsyncActionOptions<TResult>,
) {
  const lockRef = useRef(false);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(async (...args: TArgs) => {
    if (lockRef.current) {
      return undefined;
    }

    lockRef.current = true;
    setIsRunning(true);
    setError(null);

    try {
      const result = await action(...args);
      await options?.onSuccess?.(result);
      return result;
    } catch (caughtError) {
      const resolvedError = caughtError instanceof Error ? caughtError : new Error("Unknown error");
      setError(resolvedError.message);
      await options?.onError?.(resolvedError);
      throw resolvedError;
    } finally {
      lockRef.current = false;
      setIsRunning(false);
    }
  }, [action, options]);

  return {
    run,
    isRunning,
    error,
    clearError: () => setError(null),
  };
}
