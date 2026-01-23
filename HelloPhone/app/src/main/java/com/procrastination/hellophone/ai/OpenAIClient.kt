package com.procrastination.hellophone.ai

import android.graphics.Bitmap
import android.util.Base64
import android.util.Log
import com.google.gson.Gson
import com.google.gson.annotations.SerializedName
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Response
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.Body
import retrofit2.http.Header
import retrofit2.http.POST
import java.io.ByteArrayOutputStream
import java.util.concurrent.TimeUnit

interface OpenAIApi {
    @POST("v1/chat/completions")
    suspend fun createChatCompletion(
        @Header("Authorization") authorization: String,
        @Body request: ChatCompletionRequest
    ): Response<ChatCompletionResponse>
}

data class ChatCompletionRequest(
    val model: String = "gpt-4o",
    val messages: List<Message>,
    @SerializedName("max_tokens")
    val maxTokens: Int = 200
)

data class Message(
    val role: String,
    val content: Any // Can be String or List<ContentPart>
)

data class ContentPart(
    val type: String,
    val text: String? = null,
    @SerializedName("image_url")
    val imageUrl: ImageUrl? = null
)

data class ImageUrl(
    val url: String,
    val detail: String = "low"
)

data class ChatCompletionResponse(
    val choices: List<Choice>
)

data class Choice(
    val message: MessageContent
)

data class MessageContent(
    val content: String
)

class OpenAIClient(private val apiKey: String) {

    companion object {
        private const val TAG = "OpenAIClient"
        private const val BASE_URL = "https://api.openai.com/"
    }

    private val api: OpenAIApi by lazy {
        val logging = HttpLoggingInterceptor().apply {
            level = HttpLoggingInterceptor.Level.BASIC
        }

        val client = OkHttpClient.Builder()
            .addInterceptor(logging)
            .connectTimeout(30, TimeUnit.SECONDS)
            .readTimeout(60, TimeUnit.SECONDS)
            .writeTimeout(60, TimeUnit.SECONDS)
            .build()

        Retrofit.Builder()
            .baseUrl(BASE_URL)
            .client(client)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(OpenAIApi::class.java)
    }

    private val gson = Gson()

    suspend fun analyzeProductivity(bitmap: Bitmap): ProductivityAnalysisResult? {
        try {
            val base64Image = bitmapToBase64(bitmap)

            val systemPrompt = """You are a gentle productivity assistant. Analyze the screenshots and webcam image to determine if the user is being productive during their deep work session.

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

            val contentParts = listOf(
                ContentPart(
                    type = "text",
                    text = "Analyze these captures from my work session. Am I being productive?"
                ),
                ContentPart(
                    type = "image_url",
                    imageUrl = ImageUrl(
                        url = "data:image/jpeg;base64,$base64Image",
                        detail = "low"
                    )
                )
            )

            val messages = listOf(
                Message(role = "system", content = systemPrompt),
                Message(role = "user", content = contentParts)
            )

            val request = ChatCompletionRequest(messages = messages)

            val response = api.createChatCompletion(
                authorization = "Bearer $apiKey",
                request = request
            )

            if (!response.isSuccessful) {
                Log.e(TAG, "API error: ${response.code()} - ${response.errorBody()?.string()}")
                return null
            }

            val content = response.body()?.choices?.firstOrNull()?.message?.content
            if (content == null) {
                Log.e(TAG, "Empty response from API")
                return null
            }

            return parseResponse(content)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to analyze productivity", e)
            return null
        }
    }

    private fun bitmapToBase64(bitmap: Bitmap): String {
        val outputStream = ByteArrayOutputStream()
        bitmap.compress(Bitmap.CompressFormat.JPEG, 85, outputStream)
        val bytes = outputStream.toByteArray()
        return Base64.encodeToString(bytes, Base64.NO_WRAP)
    }

    private fun parseResponse(content: String): ProductivityAnalysisResult {
        try {
            var jsonContent = content

            // Handle markdown code blocks
            if (jsonContent.contains("```json")) {
                jsonContent = jsonContent.substringAfter("```json").substringBefore("```")
            } else if (jsonContent.contains("```")) {
                jsonContent = jsonContent.substringAfter("```").substringBefore("```")
            }

            val data = gson.fromJson(jsonContent.trim(), Map::class.java)
            val productive = data["productive"] as? Boolean ?: true
            val reason = data["reason"] as? String ?: "Analysis complete."

            return ProductivityAnalysisResult(productive, reason)
        } catch (e: Exception) {
            Log.w(TAG, "Failed to parse JSON, inferring from text", e)
            val isProductive = content.lowercase().contains("productive") &&
                    !content.lowercase().contains("not productive")
            val reason = if (content.length > 200) content.take(200) else content
            return ProductivityAnalysisResult(isProductive, reason)
        }
    }
}

data class ProductivityAnalysisResult(
    val productive: Boolean,
    val reason: String
)
