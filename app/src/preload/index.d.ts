import { ElectronAPI } from '@electron-toolkit/preload'
import type { Veraframe } from './index'

declare global {
  interface Window {
    electron: ElectronAPI
    veraframe: Veraframe
  }
}
