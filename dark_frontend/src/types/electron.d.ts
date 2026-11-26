declare global {
  interface Window {
    darkDesktop?: {
      onToggleInput: (callback: (active: boolean) => void) => () => void;
      onToggleFiles: (callback: (active: boolean) => void) => () => void;
      onToggleInterfaces: (callback: (active: boolean) => void) => () => void;
      onOpenConfig?: (callback: () => void) => () => void;
      closeInterfaces: () => void;
      onFocusLockInput: (callback: () => void) => () => void;
      uiReady: () => void;
      closeInput: () => void;
      /** El fondo de HollOSW está a la vista: el input es el de esa superficie. */
      setDesktopShown: (shown: boolean) => void;
      closeFileModal: () => void;
      setClickable: (clickable: boolean) => void;
      setLockMode: (locked: boolean) => void;
      getLockPasswordStatus: () => Promise<{
        configured: boolean;
        readyToken: string | null;
      }>;
      createLockPassword: (password: string) => Promise<{
        created: boolean;
        unlockToken: string;
      }>;
      verifyLockPassword: (password: string) => Promise<{
        matches: boolean;
        unlockToken: string | null;
      }>;
      /** Autoriza un único reemplazo del archivo de contraseña en el próximo bloqueo. */
      armLockPasswordChange: () => Promise<{ armed: boolean }>;
      replaceLockPassword: (password: string) => Promise<{
        replaced: boolean;
        unlockToken: string;
      }>;

      // Modal de archivos
      pickFiles: () => Promise<string[]>;
      getPathForFile: (file: File) => string;
      setModalOpen: (open: boolean) => void;
      onOpenFileModal: (callback: () => void) => () => void;
      requestFileModal: () => void;
      /**
       * `size` son los bytes que midió el proceso principal, o `null` cuando no los
       * midió: nunca un cero que se leería como «archivo vacío». `ok` a `false` es
       * el archivo que no se pudo ni estadizar; el motivo lo dice `error`.
       */
      readFilePreview: (filePath: string) => Promise<{
        ok?: boolean;
        isText: boolean;
        preview?: string;
        size?: number | null;
        error?: string | null;
      }>;
    };
  }
}

export {};
