"""AI-powered productivity analysis using OpenAI Vision API."""

import base64
import json
import os
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image

# Load environment variables
load_dotenv()


class ProductivityResult:
    def __init__(self, productive: bool, reason: str, timestamp: datetime):
        self.productive = productive
        self.reason = reason
        self.timestamp = timestamp

    def to_dict(self) -> dict:
        return {
            "productive": self.productive,
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat()
        }


class AIAnalyzer:
    def __init__(self, results_dir: str = "results"):
        self._client: Optional[OpenAI] = None
        self._results_dir = Path(results_dir)
        self._results_dir.mkdir(exist_ok=True)
        self._recent_results: list[ProductivityResult] = []
        self._max_recent = 20

    def _get_client(self) -> OpenAI:
        """Get or create OpenAI client."""
        if self._client is None:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY not found in environment variables")
            self._client = OpenAI(api_key=api_key)
        return self._client

    def analyze(self, image: Image.Image) -> Optional[ProductivityResult]:
        """
        Analyze an image for productivity.

        Args:
            image: PIL Image to analyze

        Returns:
            ProductivityResult with productive status and reason
        """
        try:
            client = self._get_client()

            # Convert image to base64
            buffered = BytesIO()
            image.save(buffered, format="JPEG", quality=85)
            base64_image = base64.b64encode(buffered.getvalue()).decode("utf-8")

            # Send to OpenAI Vision API
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": """You are a gentle productivity assistant. Analyze the screenshots and webcam image to determine if the user is being productive during their deep work session.

Look for:
- Code editors, documentation, work-related applications = productive
- Social media, entertainment sites, games = not productive
- Reading/research that appears work-related = productive

Respond with JSON only:
{
    "productive": true/false,
    "reason": "A brief, encouraging message (max 2 sentences). If not productive, be gentle and understanding, not judgmental."
}

Examples of good reasons:
- Productive: "Great focus on your code! Keep up the excellent work."
- Not productive: "I notice you might be taking a quick break. When you're ready, let's get back to the deep work session."
"""
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Analyze these captures from my work session. Am I being productive?"
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}",
                                    "detail": "low"  # Use low detail to reduce costs
                                }
                            }
                        ]
                    }
                ],
                max_tokens=200
            )

            # Parse response
            content = response.choices[0].message.content
            # Try to extract JSON from the response
            try:
                # Handle case where response might have markdown code blocks
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]

                data = json.loads(content.strip())
                result = ProductivityResult(
                    productive=data.get("productive", True),
                    reason=data.get("reason", "Analysis complete."),
                    timestamp=datetime.now()
                )
            except json.JSONDecodeError:
                # If JSON parsing fails, try to infer from text
                is_productive = "productive" in content.lower() and "not productive" not in content.lower()
                result = ProductivityResult(
                    productive=is_productive,
                    reason=content[:200] if len(content) > 200 else content,
                    timestamp=datetime.now()
                )

            # Store result
            self._recent_results.append(result)
            if len(self._recent_results) > self._max_recent:
                self._recent_results.pop(0)

            # Save result to file
            self._save_result(result)

            return result

        except Exception as e:
            print(f"AI analysis error: {e}")
            return None

    def _save_result(self, result: ProductivityResult):
        """Save analysis result to JSON file."""
        results_file = self._results_dir / "analysis_results.json"

        # Load existing results
        existing = []
        if results_file.exists():
            try:
                with open(results_file, "r") as f:
                    existing = json.load(f)
            except (json.JSONDecodeError, IOError):
                existing = []

        # Append new result
        existing.append(result.to_dict())

        # Keep only last 100 results
        if len(existing) > 100:
            existing = existing[-100:]

        # Save
        with open(results_file, "w") as f:
            json.dump(existing, f, indent=2)

    def get_recent_results(self, count: int = 10) -> list[ProductivityResult]:
        """Get the most recent analysis results."""
        return self._recent_results[-count:]


# Global analyzer instance
ai_analyzer = AIAnalyzer()
