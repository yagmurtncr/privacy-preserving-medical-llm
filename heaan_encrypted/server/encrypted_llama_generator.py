#!/usr/bin/env python3
"""
Encrypted Llama Text Generator
LlamaTextGenerator'ın in-memory encrypted versiyonu

Model RAM'de AES-256-GCM ile şifreli, sadece inference sırasında decrypt edilir.
"""

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from typing import Optional, Dict, Any
import time
import os
import gc
from heaan_encrypted.server.layerwise_encrypted_model import LayerwiseEncryptedModelWrapper


class EncryptedLlamaTextGenerator:
    """
    Encrypted Llama 3.1 8B text generator
    Model RAM'de şifreli, inference sırasında geçici decrypt
    """
    
    def __init__(self,
                 model_name: str = "meta-llama/Meta-Llama-3.1-8B-Instruct",
                 device: str = "cuda" if torch.cuda.is_available() else "cpu",
                 max_length: int = 512,
                 temperature: float = 0.7,
                 enable_encryption: bool = True):
        """
        Encrypted Llama text generator
        
        Args:
            model_name: HuggingFace model ID
            device: cuda or cpu
            enable_encryption: True = in-memory encrypted, False = normal
        """
        self.device = device
        self.max_length = max_length
        self.temperature = temperature
        self.enable_encryption = enable_encryption
        self.model_name = model_name
        
        print(f"\n{'='*80}")
        print(f"🔐 Loading Llama 3.1 8B (Encryption: {'ON' if enable_encryption else 'OFF'})...")
        print(f"{'='*80}")
        
        start = time.time()
        
        try:
            # Tokenizer yükle (always plaintext, small size)
            print("📝 Loading tokenizer...")
            self.tokenizer = AutoTokenizer.from_pretrained(
                model_name,
                trust_remote_code=True
            )
            
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token
            
            print("✅ Tokenizer loaded")
            
            # Model yükle
            if enable_encryption:
                # ===== ENCRYPTED MODE =====
                print(f"\n🔐 Loading model in ENCRYPTED mode...")
                
                # Check if pre-encrypted model exists on disk
                from pathlib import Path
                import os
                # Use absolute path based on project root
                project_root = Path(__file__).parent.parent.parent
                encrypted_model_path = project_root / "encrypted_models" / f"{model_name.replace('/', '_')}_encrypted.enc"
                
                print(f"   [DEBUG] Looking for: {encrypted_model_path}")
                print(f"   [DEBUG] Exists: {encrypted_model_path.exists()}")
                
                if encrypted_model_path.exists():
                    # ===== LOAD FROM DISK (FAST!) =====
                    print(f"   📂 Found pre-encrypted model on disk!")
                    print(f"   Loading from: {encrypted_model_path}")
                    
                    self.encrypted_wrapper = EncryptedModelWrapper.load_encrypted_model(
                        str(encrypted_model_path),
                        self.tokenizer
                    )
                    self.model = None
                    
                    print("   ✅ Pre-encrypted model loaded from disk!")
                    
                else:
                    # ===== CREATE NEW (SLOW, FIRST TIME ONLY) =====
                    print("   ⚠️  No pre-encrypted model found on disk")
                    print("   🔒 Creating new LAYER-WISE encrypted model...")
                    print("   ℹ️  Each layer encrypted separately (memory efficient!)")
                    
                    # Load model in INT8 (smaller, layer-wise encryption compatible!)
                    print("   📦 Loading INT8 model...")
                    
                    if device == "cuda":
                        model = AutoModelForCausalLM.from_pretrained(
                            model_name,
                            torch_dtype=torch.float16,
                            device_map="auto",
                            trust_remote_code=True
                        )
                    else:
                        model = AutoModelForCausalLM.from_pretrained(
                            model_name,
                            torch_dtype=torch.float32,
                            device_map=None,
                            trust_remote_code=True
                        )
                        model = model.to(device)
                    
                    print(f"   ✅ FP16 model loaded (~16 GB)")
                    
                    model.eval()
                    
                    # Freeze weights
                    for param in model.parameters():
                        param.requires_grad = False
                    
                    # Wrap with LAYER-WISE encryption
                    print("\n🔒 Encrypting model layer-by-layer...")
                    self.encrypted_wrapper = LayerwiseEncryptedModelWrapper(
                        model=model,
                        tokenizer=self.tokenizer
                    )
                    
                    # Model is now encrypted, no plaintext reference
                    self.model = None
                    
                    print("✅ Model encrypted layer-by-layer in RAM!")
                    
                    # Note: Disk saving for layer-wise will be implemented later if needed
                
            else:
                # ===== NORMAL MODE (no encryption) =====
                print(f"\n⚠️  Loading model in NORMAL mode (no encryption)...")
                
                if device == "cuda":
                    self.model = AutoModelForCausalLM.from_pretrained(
                        model_name,
                        torch_dtype=torch.float16,
                        device_map="auto",
                        trust_remote_code=True
                    )
                else:
                    self.model = AutoModelForCausalLM.from_pretrained(
                        model_name,
                        torch_dtype=torch.float32,
                        device_map=None,
                        trust_remote_code=True
                    )
                    self.model = self.model.to(device)
                
                self.model.eval()
                
                # Freeze weights
                for param in self.model.parameters():
                    param.requires_grad = False
                
                self.encrypted_wrapper = None
                
                print("✅ Model loaded (plaintext in RAM)")
            
            elapsed = time.time() - start
            print(f"\n✅ Llama loaded in {elapsed:.1f}s")
            print(f"   Device: {self.device}")
            print(f"   Model: {model_name}")
            print(f"   Encryption: {'ENABLED ✅' if enable_encryption else 'DISABLED ⚠️'}")
            print("=" * 80)
            
        except Exception as e:
            print(f"❌ FATAL: Failed to load Llama: {e}")
            raise RuntimeError(f"Llama 3.1 8B failed to load: {e}")
    
    def generate(self,
                prompt: str,
                max_new_tokens: int = 256,
                temperature: float = 0.7,
                do_sample: bool = True) -> str:
        """
        Text üret
        
        Encrypted mode: Model decrypt → inference → re-encrypt
        Normal mode: Direct inference
        """
        
        if self.enable_encryption:
            # ===== ENCRYPTED INFERENCE =====
            return self.encrypted_wrapper.inference(
                input_text=prompt,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                do_sample=do_sample
            )
        else:
            # ===== NORMAL INFERENCE =====
            inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)
            
            with torch.no_grad():
                outputs = self.model.generate(
                    inputs.input_ids,
                    max_new_tokens=max_new_tokens,
                    temperature=temperature,
                    do_sample=do_sample,
                    pad_token_id=self.tokenizer.eos_token_id
                )
            
            response = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
            return response
    
    def _format_medical_prompt(self, query: str) -> str:
        """Medical domain için optimized prompt"""
        system_prompt = """Sen uzman bir tıbbi AI asistanısın. Türkçe olarak doğru, kanıta dayalı tıbbi bilgi sun.
ÖNEMLİ KURALLAR:
- SADECE ANALİZ YAP - Soruyu veya laboratuvar sonuçlarını TEKRARLAMA
- Direkt değerlendirme ile başla
- Net, profesyonel ve hasta odaklı ol
- Güncel tıbbi kılavuzlara dayalı bilgi ver
- Sağlık profesyonelleri için uygun dil kullan
NOT: Bu bilgilendirme amaçlıdır. Tanı ve tedavi için mutlaka sağlık kuruluşuna başvurulmalıdır."""
        
        return f"{system_prompt}\n{query}"
    
    def _extract_response(self, full_text: str, original_query: str) -> str:
        """System prompt ve query echo'larını temizle"""
        import re
        
        # System prompt'u kaldır (agresif)
        patterns_to_remove = [
            r'Sen uzman bir tıbbi AI.*?başvurulmalıdır\.',
            r'ÖNEMLİ KURALLAR:.*?başvurulmalıdır\.',
            r'NOT:.*?başvurulmalıdır\.',
        ]
        
        cleaned = full_text
        for pattern in patterns_to_remove:
            cleaned = re.sub(pattern, '', cleaned, flags=re.DOTALL | re.IGNORECASE)
        
        # Query echo'sunu kaldır
        if original_query in cleaned:
            cleaned = cleaned.replace(original_query, '', 1)
        
        # İlk 100 karakteri kontrol et (bazen query kısmi echo)
        query_words = original_query.split()[:5]  # İlk 5 kelime
        for word in query_words:
            if len(word) > 3:  # Küçük kelimeler skip
                cleaned = cleaned.replace(word, '', 1)
        
        # Trim whitespace
        cleaned = cleaned.strip()
        
        # Eğer boş kaldıysa, original dön
        if not cleaned or len(cleaned) < 20:
            return full_text
        
        return cleaned
    
    def generate_medical_text(self,
                             query: str,
                             max_new_tokens: int = 256,
                             temperature: float = 0.7) -> Dict[str, Any]:
        """
        Medical text generation
        
        Returns:
            Dict with 'text', 'prompt_tokens', 'completion_tokens', 'total_tokens'
        """
        start = time.time()
        
        # Format prompt
        formatted_prompt = self._format_medical_prompt(query)
        
        # Generate
        full_response = self.generate(
            prompt=formatted_prompt,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            do_sample=True
        )
        
        # Extract clean response
        cleaned_response = self._extract_response(full_response, query)
        
        elapsed = time.time() - start
        
        return {
            "text": cleaned_response,
            "processing_time_sec": round(elapsed, 2),
            "prompt_length": len(formatted_prompt),
            "response_length": len(cleaned_response)
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Generator istatistikleri"""
        
        stats = {
            "model_name": self.model_name,
            "device": self.device,
            "encryption_enabled": self.enable_encryption,
            "max_length": self.max_length,
            "temperature": self.temperature
        }
        
        if self.enable_encryption and self.encrypted_wrapper:
            # Encryption stats
            enc_stats = self.encrypted_wrapper.get_stats()
            stats["encryption_stats"] = enc_stats
        else:
            stats["encryption_stats"] = None
        
        return stats


# Test
if __name__ == "__main__":
    import os
    
    # Set encryption key
    os.environ["MODEL_ENCRYPTION_KEY"] = "test-key-for-demo"
    
    print("\n" + "=" * 80)
    print("🧪 ENCRYPTED LLAMA GENERATOR TEST")
    print("=" * 80)
    
    # Test with encryption
    print("\n1️⃣ TEST: Encrypted Mode")
    generator = EncryptedLlamaTextGenerator(
        device="cuda" if torch.cuda.is_available() else "cpu",
        enable_encryption=True
    )
    
    result = generator.generate_medical_text(
        query="Diyabet nedir?",
        max_new_tokens=100
    )
    
    print(f"\n📄 Response: {result['text'][:300]}...")
    print(f"⏱️  Time: {result['processing_time_sec']}s")
    
    # Stats
    print("\n📊 Stats:")
    stats = generator.get_stats()
    print(stats)
    
    print("\n✅ TEST COMPLETED!")

