import { useCallback, useEffect, useMemo, useState } from "react";
import type { ApiError, ApiResource } from "../types/student";

interface ResourceState<T> {
  requestToken: object;
  data: T | null;
  error: ApiError | null;
}

const INVALID_RESPONSE_MESSAGE =
  "Máy chủ trả về phản hồi không hợp lệ. Vui lòng thử lại sau.";
const INVALID_DATA_MESSAGE =
  "Dữ liệu máy chủ trả về không hợp lệ. Vui lòng thử lại sau.";
const CONNECTION_ERROR_MESSAGE =
  "Không thể kết nối đến máy chủ. Vui lòng kiểm tra kết nối và thử lại.";
const REQUEST_ERROR_MESSAGE = "Yêu cầu không thành công. Vui lòng thử lại.";

function errorFromResponse(response: Response, payload: unknown): ApiError {
  const error: ApiError = {
    statusCode: response.status,
    message: REQUEST_ERROR_MESSAGE,
  };

  if (
    payload !== null &&
    typeof payload === "object" &&
    !Array.isArray(payload)
  ) {
    if ("statusCode" in payload && typeof payload.statusCode === "number") {
      error.statusCode = payload.statusCode;
    }
    if (
      "message" in payload &&
      typeof payload.message === "string" &&
      payload.message.trim().length > 0
    ) {
      error.message = payload.message;
    }
    if ("timestamp" in payload && typeof payload.timestamp === "string") {
      error.timestamp = payload.timestamp;
    }
    if ("path" in payload && typeof payload.path === "string") {
      error.path = payload.path;
    }
  }

  return error;
}

export function useApiResource<T>(url: string | null): ApiResource<T> {
  const [reloadVersion, setReloadVersion] = useState(0);
  const [resourceState, setResourceState] = useState<ResourceState<T> | null>(
    null,
  );
  const requestToken = useMemo(() => ({ url, reloadVersion }), [url, reloadVersion]);

  useEffect(() => {
    if (url === null) {
      return;
    }

    const controller = new AbortController();
    let active = true;

    const load = async () => {
      try {
        const response = await fetch(url, {
          headers: { Accept: "application/json" },
          signal: controller.signal,
        });

        let payload: unknown;
        try {
          payload = await response.json();
        } catch {
          if (active && !controller.signal.aborted) {
            setResourceState({
              requestToken,
              data: null,
              error: {
                statusCode: response.status,
                message: INVALID_RESPONSE_MESSAGE,
              },
            });
          }
          return;
        }

        if (!active || controller.signal.aborted) {
          return;
        }

        if (!response.ok) {
          setResourceState({
            requestToken,
            data: null,
            error: errorFromResponse(response, payload),
          });
          return;
        }

        if (
          payload === null ||
          typeof payload !== "object" ||
          Array.isArray(payload) ||
          !("data" in payload) ||
          payload.data == null
        ) {
          setResourceState({
            requestToken,
            data: null,
            error: {
              statusCode: response.status,
              message: INVALID_DATA_MESSAGE,
            },
          });
          return;
        }

        setResourceState({
          requestToken,
          data: payload.data as T,
          error: null,
        });
      } catch {
        if (!active || controller.signal.aborted) {
          return;
        }

        setResourceState({
          requestToken,
          data: null,
          error: {
            statusCode: null,
            message: CONNECTION_ERROR_MESSAGE,
          },
        });
      }
    };

    void load();

    return () => {
      active = false;
      controller.abort();
    };
  }, [requestToken, url]);

  const refetch = useCallback(() => {
    setReloadVersion((version) => version + 1);
  }, []);

  if (url === null) {
    return { data: null, loading: false, error: null, refetch };
  }

  if (resourceState?.requestToken === requestToken) {
    return {
      data: resourceState.data,
      loading: false,
      error: resourceState.error,
      refetch,
    };
  }

  return { data: null, loading: true, error: null, refetch };
}
