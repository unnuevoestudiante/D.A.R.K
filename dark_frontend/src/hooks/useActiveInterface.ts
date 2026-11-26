import { useCallback, useEffect, useState } from "react";
import {
  DEFAULT_INTERFACE_ID,
  getAllInterfaces,
  getInterface,
} from "@/lib/interfaces/registry";
import type { DarkInterfaceDefinition } from "@/types/interfaces";

const STORAGE_KEY = "dark:active_interface_id";
const EVENT_NAME = "dark:interface_changed";

export function useActiveInterface(bridgeInterfaceId?: string | null) {
  const [interfaceId, setInterfaceId] = useState<string>(() => {
    if (typeof window === "undefined") return DEFAULT_INTERFACE_ID;

    // 1. Parámetro de URL (útil para embedding o depuración)
    const params = new URLSearchParams(window.location.search);
    const fromUrl = params.get("interface") || params.get("ui");
    if (fromUrl) return fromUrl;

    // 2. LocalStorage
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) return saved;
    } catch (_) {
      // Ignorar fallo de almacenamiento
    }

    return DEFAULT_INTERFACE_ID;
  });

  // Si el backend/bridge propaga un cambio de interfaz, sincronizar
  useEffect(() => {
    if (bridgeInterfaceId && bridgeInterfaceId !== interfaceId) {
      setInterfaceId(bridgeInterfaceId);
      try {
        localStorage.setItem(STORAGE_KEY, bridgeInterfaceId);
      } catch (_) {}
    }
  }, [bridgeInterfaceId]);

  // Escuchar eventos locales entre pestañas/componentes
  useEffect(() => {
    const handleStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY && e.newValue) {
        setInterfaceId(e.newValue);
      }
    };

    const handleCustom = (e: Event) => {
      const customEvent = e as CustomEvent<string>;
      if (customEvent.detail) {
        setInterfaceId(customEvent.detail);
      }
    };

    window.addEventListener("storage", handleStorage);
    window.addEventListener(EVENT_NAME, handleCustom);
    return () => {
      window.removeEventListener("storage", handleStorage);
      window.removeEventListener(EVENT_NAME, handleCustom);
    };
  }, []);

  const changeInterface = useCallback((newId: string) => {
    setInterfaceId(newId);
    try {
      localStorage.setItem(STORAGE_KEY, newId);
    } catch (_) {}

    // Notificar a otros escuchas locales
    window.dispatchEvent(
      new CustomEvent<string>(EVENT_NAME, { detail: newId }),
    );
  }, []);

  const activeInterface = getInterface(interfaceId);
  const availableInterfaces = getAllInterfaces();

  return {
    interfaceId: activeInterface.id,
    activeInterface,
    availableInterfaces,
    setInterface: changeInterface,
  };
}
