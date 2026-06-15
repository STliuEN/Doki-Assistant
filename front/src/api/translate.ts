import { endpoints } from './endpoints'

export interface DialogueTranslatePayload {
  language_a: string
  language_b: string
  text: string
  model_config_id?: string
  custom_instruction?: string
  fast_mode?: boolean
}

export const translateApi = {
  dialogueStream: endpoints.dialogueTranslateStream,
}
