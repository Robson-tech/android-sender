package com.robson.photosender

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.net.Uri
import android.os.Bundle
import android.util.Log
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.core.*
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.robson.photosender.databinding.ActivityMainBinding
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.*
import java.net.Socket
import java.nio.ByteBuffer
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

class MainActivity : AppCompatActivity() {
    private lateinit var binding: ActivityMainBinding
    private var imageCapture: ImageCapture? = null
    private lateinit var cameraExecutor: ExecutorService
    
    companion object {
        private const val TAG = "PhotoSender"
        private const val FILENAME_FORMAT = "yyyy-MM-dd-HH-mm-ss-SSS"
        private const val REQUEST_CODE_PERMISSIONS = 10
        private val REQUIRED_PERMISSIONS = mutableListOf(
            Manifest.permission.CAMERA
        ).toTypedArray()
    }
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        
        // Configurar valores padrão
        binding.editTextServerIp.setText("192.168.1.100") // Altere para o IP do seu servidor
        binding.editTextServerPort.setText("5001")
        
        // Configurar botão
        binding.buttonTakeAndSend.setOnClickListener {
            takePhotoAndSend()
        }
        
        // Request camera permissions
        if (allPermissionsGranted()) {
            startCamera()
        } else {
            requestPermissions()
        }
        
        cameraExecutor = Executors.newSingleThreadExecutor()
    }
    
    private fun takePhotoAndSend() {
        val imageCapture = imageCapture ?: return
        
        binding.buttonTakeAndSend.isEnabled = false
        binding.textViewStatus.text = "Capturando foto..."
        
        val outputFileOptions = ImageCapture.OutputFileOptions.Builder(
            createTempFile("photo", ".jpg", cacheDir)
        ).build()
        
        imageCapture.takePicture(
            outputFileOptions,
            ContextCompat.getMainExecutor(this),
            object : ImageCapture.OnImageSavedCallback {
                override fun onError(exception: ImageCaptureException) {
                    Log.e(TAG, "Photo capture failed: ${exception.message}", exception)
                    runOnUiThread {
                        binding.textViewStatus.text = "Erro ao capturar foto"
                        binding.buttonTakeAndSend.isEnabled = true
                        Toast.makeText(this@MainActivity, "Erro ao capturar foto", Toast.LENGTH_SHORT).show()
                    }
                }
                
                override fun onImageSaved(output: ImageCapture.OutputFileResults) {
                    Log.d(TAG, "Photo capture succeeded")
                    runOnUiThread {
                        binding.textViewStatus.text = "Foto capturada! Enviando..."
                    }
                    
                    // Enviar foto
                    output.savedUri?.let { uri ->
                        sendPhotoToServer(uri)
                    }
                }
            }
        )
    }
    
    private fun sendPhotoToServer(imageUri: Uri) {
        val serverIp = binding.editTextServerIp.text.toString().trim()
        val serverPort = binding.editTextServerPort.text.toString().trim().toIntOrNull() ?: 5001
        
        if (serverIp.isEmpty()) {
            runOnUiThread {
                binding.textViewStatus.text = "IP do servidor não pode estar vazio"
                binding.buttonTakeAndSend.isEnabled = true
            }
            return
        }
        
        lifecycleScope.launch(Dispatchers.IO) {
            try {
                // Ler e processar imagem
                val imageBytes = processImage(imageUri)
                
                withContext(Dispatchers.Main) {
                    binding.textViewStatus.text = "Conectando ao servidor..."
                }
                
                // Conectar ao servidor
                val socket = Socket(serverIp, serverPort)
                
                withContext(Dispatchers.Main) {
                    binding.textViewStatus.text = "Enviando foto..."
                }
                
                // Enviar tamanho da imagem (4 bytes - big-endian)
                val sizeBytes = ByteBuffer.allocate(4).putInt(imageBytes.size).array()
                socket.getOutputStream().write(sizeBytes)
                
                // Enviar imagem
                socket.getOutputStream().write(imageBytes)
                socket.getOutputStream().flush()
                
                // Aguardar confirmação
                val response = ByteArray(2)
                socket.getInputStream().read(response)
                
                socket.close()
                
                withContext(Dispatchers.Main) {
                    binding.textViewStatus.text = "Foto enviada com sucesso!"
                    binding.buttonTakeAndSend.isEnabled = true
                    Toast.makeText(this@MainActivity, "Foto enviada!", Toast.LENGTH_SHORT).show()
                }
                
            } catch (e: Exception) {
                Log.e(TAG, "Error sending photo", e)
                withContext(Dispatchers.Main) {
                    binding.textViewStatus.text = "Erro ao enviar foto: ${e.message}"
                    binding.buttonTakeAndSend.isEnabled = true
                    Toast.makeText(this@MainActivity, "Erro ao enviar foto", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }
    
    private fun processImage(imageUri: Uri): ByteArray {
        // Ler imagem
        val inputStream = contentResolver.openInputStream(imageUri)
        val originalBitmap = BitmapFactory.decodeStream(inputStream)
        inputStream?.close()
        
        // Redimensionar se necessário (máximo 1280px de largura)
        val maxWidth = 1280
        val bitmap = if (originalBitmap.width > maxWidth) {
            val ratio = maxWidth.toFloat() / originalBitmap.width
            val newHeight = (originalBitmap.height * ratio).toInt()
            Bitmap.createScaledBitmap(originalBitmap, maxWidth, newHeight, true)
        } else {
            originalBitmap
        }
        
        // Converter para JPEG
        val outputStream = ByteArrayOutputStream()
        bitmap.compress(Bitmap.CompressFormat.JPEG, 80, outputStream)
        
        // Limpar recursos
        if (bitmap != originalBitmap) {
            bitmap.recycle()
        }
        originalBitmap.recycle()
        
        return outputStream.toByteArray()
    }
    
    private fun startCamera() {
        val cameraProviderFuture = ProcessCameraProvider.getInstance(this)
        
        cameraProviderFuture.addListener({
            val cameraProvider: ProcessCameraProvider = cameraProviderFuture.get()
            
            val preview = Preview.Builder().build().also {
                it.setSurfaceProvider(binding.viewFinder.surfaceProvider)
            }
            
            imageCapture = ImageCapture.Builder().build()
            
            val cameraSelector = CameraSelector.DEFAULT_BACK_CAMERA
            
            try {
                cameraProvider.unbindAll()
                cameraProvider.bindToLifecycle(
                    this, cameraSelector, preview, imageCapture
                )
            } catch (exc: Exception) {
                Log.e(TAG, "Use case binding failed", exc)
            }
            
        }, ContextCompat.getMainExecutor(this))
    }
    
    private fun requestPermissions() {
        activityResultLauncher.launch(REQUIRED_PERMISSIONS)
    }
    
    private fun allPermissionsGranted() = REQUIRED_PERMISSIONS.all {
        ContextCompat.checkSelfPermission(baseContext, it) == PackageManager.PERMISSION_GRANTED
    }
    
    private val activityResultLauncher =
        registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { permissions ->
            var permissionGranted = true
            permissions.entries.forEach {
                if (it.key in REQUIRED_PERMISSIONS && it.value == false)
                    permissionGranted = false
            }
            if (!permissionGranted) {
                Toast.makeText(baseContext, "Permissão da câmera é necessária.", Toast.LENGTH_SHORT).show()
            } else {
                startCamera()
            }
        }
    
    override fun onDestroy() {
        super.onDestroy()
        cameraExecutor.shutdown()
    }
}