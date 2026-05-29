
import os
from abc import ABC, abstractmethod
from transformers import pipeline
from pydub import AudioSegment

# Optional: Azure SDK for speech
try:
    import azure.cognitiveservices.speech as speechsdk
except ImportError:
    speechsdk = None

# Ensure ffmpeg is available for pydub
os.environ["PATH"] += os.pathsep + r"C:\\Praveen\\Projects\\qa-project-domain-transcribe\\agent_framework\\models\\ffmpeg-8.0.1-essentials_build\bin"
AudioSegment.converter = os.path.join(r"C:\\Praveen\\Projects\\qa-project-domain-transcribe\\agent_framework\\models\\ffmpeg-8.0.1-essentials_build\bin", "ffmpeg.exe")


# -------------------------------
# Abstract Base Class
# -------------------------------
class STTStrategy(ABC):
    @abstractmethod
    async def transcribe(self, file_path: str, return_timestamps: bool = False) -> str:
        """Abstract method for speech-to-text transcription."""
        pass


# -------------------------------
# Hugging Face Whisper Strategy (Backward Compatible)
# -------------------------------

class HuggingFaceSTTStrategy(STTStrategy):
    def __init__(self, model_name="openai/whisper-small", local_mode=False, device="cpu"):
        """
        Initialize HuggingFace Whisper pipeline.
        :param model_name: HuggingFace model name or local path
        :param local_mode: If True, model_name should be a local path
        :param device: 'cpu' or 'cuda'
        """
        if local_mode:
            # Expect model_name to be a local path
            self.pipeline = pipeline("automatic-speech-recognition", model=model_name, device=-1)
        else:
            self.pipeline = pipeline("automatic-speech-recognition", model=model_name, device=-1)

    async def transcribe(self, file_path: str, return_timestamps: bool = False) -> str:
        kwargs = {}
        if return_timestamps:
            kwargs["return_timestamps"] = True
        try:
            result = self.pipeline(
                file_path,
                return_timestamps=True,
                chunk_length_s=30,
                stride_length_s=5
            )
        except KeyError as e:
            if str(e) == "'num_frames'":
                raise RuntimeError(
                    "Transformers ASR pipeline missing num_frames. "
                    "Ensure chunk_length_s and stride_length_s are set."
                )

        return result.get("text", "")



# -------------------------------
# Azure Cognitive Services Strategy
# -------------------------------
class AzureSTTStrategy(STTStrategy):
    def __init__(self, azure_key: str, azure_region: str):
        if not speechsdk:
            raise ImportError("Azure SDK not installed. Run: pip install azure-cognitiveservices-speech")
        self.azure_key = azure_key
        self.azure_region = azure_region

    async def transcribe(self, file_path: str, return_timestamps: bool = False) -> str:
        speech_config = speechsdk.SpeechConfig(subscription=self.azure_key, region=self.azure_region)
        audio_config = speechsdk.audio.AudioConfig(filename=file_path)
        recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
        result = recognizer.recognize_once()
        return result.text if result.reason == speechsdk.ResultReason.RecognizedSpeech else ""


# -------------------------------
# TranscriptAgent Class
# -------------------------------
class TranscriptAgent:
    def __init__(self,name, model_client, short_term_memory, long_term_memory, stt_strategy: STTStrategy):
        self.name = name
        self.model_client = model_client
        self.stm = short_term_memory
        self.ltm = long_term_memory
        self.stt_strategy = stt_strategy

    async def run(self, file_path: str) -> str:
        if not file_path:
            return "Error: No file path provided."

        # Check audio duration
        duration = self.get_audio_duration(file_path)
        if duration > 30:
            # Split audio into chunks and transcribe each
            chunks = self.split_audio(file_path, chunk_length=30)
            transcripts = []
            for chunk_path in chunks[:1]: # enable for local execution purpose 
            # for chunk_path in chunks:
                part = await self.stt_strategy.transcribe(chunk_path)
                transcripts.append(part)
            transcript = " ".join(transcripts)
        else:
            transcript = await self.stt_strategy.transcribe(file_path)

        return transcript

    def get_audio_duration(self, file_path: str) -> float:
        """Get audio duration in seconds using pydub."""
        audio = AudioSegment.from_file(file_path)
        return len(audio) / 1000.0

    def split_audio(self, file_path: str, chunk_length=30):
        """Split audio into chunks of specified length (in seconds)."""
        audio = AudioSegment.from_file(file_path)
        duration_ms = len(audio)
        chunk_ms = chunk_length * 1000
        chunks = []

        output_dir = "audio_chunks"
        os.makedirs(output_dir, exist_ok=True)

        for i in range(0, duration_ms, chunk_ms):
            chunk = audio[i:i + chunk_ms]
            chunk_path = os.path.join(output_dir, f"chunk_{i // chunk_ms}.wav")
            chunk.export(chunk_path, format="wav")
            chunks.append(chunk_path)

        return chunks
