import type { Meta, StoryObj } from "@storybook/react-vite"
import { AudioTranscriptViewer } from "@/features/evidence/components/AudioTranscriptViewer"

const segments = [
  {
    id: "seg-1",
    start: 0,
    end: 8.4,
    speaker: "A",
    text: "Before we begin, can you confirm your full name for the recording?",
  },
  {
    id: "seg-2",
    start: 8.4,
    end: 15.8,
    speaker: "B",
    text: "My name is Michael Byrne. I understand this interview is being recorded.",
  },
  {
    id: "seg-3",
    start: 15.8,
    end: 29.1,
    speaker: "A",
    text: "I want to take you back to the evening of the fourteenth. What time did you arrive at the warehouse?",
  },
  {
    id: "seg-4",
    start: 29.1,
    end: 42.6,
    speaker: "B",
    text: "It was just after nine. The south gate was already open, which was unusual for that time of night.",
  },
  {
    id: "seg-5",
    start: 42.6,
    end: 55.2,
    speaker: "A",
    text: "Did you see anyone else on the premises when you entered?",
  },
  {
    id: "seg-6",
    start: 55.2,
    end: 70.5,
    speaker: "B",
    text: "There was a dark van beside loading bay three. I could hear two people talking inside the office.",
  },
  {
    id: "seg-7",
    start: 70.5,
    end: 71.1,
    speaker: "C",
    text: "Yeah.",
  },
  {
    id: "seg-8",
    start: 71.1,
    end: 82.4,
    speaker: "A",
    text: "Let us stay with the van. Did you recognize either of the voices?",
  },
]

const meta = {
  title: "Evidence/Audio Transcript Viewer",
  component: AudioTranscriptViewer,
  parameters: {
    layout: "fullscreen",
  },
} satisfies Meta<typeof AudioTranscriptViewer>

export default meta
type Story = StoryObj<typeof meta>

export const DiarizedInterview: Story = {
  args: {
    documentName: "Interview — Michael Byrne — 14 May 2026.mp3",
    segments,
    speakers: {
      A: "Det. Sarah Keane",
      B: "Michael Byrne",
    },
    speakerMerges: {},
    onSpeakerSettingsChange: async (settings) => settings,
  },
  decorators: [
    (Story) => (
      <div className="h-screen w-screen">
        <Story />
      </div>
    ),
  ],
}
