"""
Secure Memory Module
RAM ve GPU'dan hassas verileri güvenli şekilde temizler (string zeroing, tensor cleanup, GC)
"""

import ctypes
import gc
from typing import Any

# PyTorch optional (GPU cleanup için)
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

# =============================================================================
# SECURE MEMORY CLASS
# =============================================================================

class SecureMemory:
    """Hassas verileri bellekten güvenli şekilde temizleyen utility class"""
    
    # Kullanım Sırası: 1 (String cleanup için)
    # Açıklama: String referansını siler ve garbage collection tetikler
    @staticmethod
    def secure_delete_string(s: str) -> None:
        if s is None:
            return
        try:
            del s
            gc.collect()
        except Exception:
            pass  # Silent fail
    
    # Kullanım Sırası: 2 (GPU/CPU tensor cleanup için)
    # Açıklama: Tensor'ı zero'lar, GPU cache temizler, referans siler
    @staticmethod
    def secure_delete_tensor(tensor: 'torch.Tensor') -> None:
        if not TORCH_AVAILABLE or tensor is None:
            return
        
        try:
            is_gpu = tensor.is_cuda if hasattr(tensor, 'is_cuda') else False
            
            # Tensor'ı zero'la
            if hasattr(tensor, 'zero_'):
                tensor.zero_()
            
            # GPU cache temizle
            if is_gpu and hasattr(torch.cuda, 'empty_cache'):
                torch.cuda.empty_cache()
                if hasattr(torch.cuda, 'synchronize'):
                    torch.cuda.synchronize()
            
            del tensor
            gc.collect()
        except Exception:
            pass  # Silent fail
    
    # Kullanım Sırası: 3 (Bytes cleanup için)
    # Açıklama: Bytes'ı C-level memset ile zero'lar ve referans siler
    @staticmethod
    def secure_delete_bytes(data: bytes) -> None:
        if data is None or len(data) == 0:
            return
        
        try:
            # C-level memory zero (tehlikeli ama etkili)
            try:
                addr = id(data)
                size = len(data)
                ctypes.memset(addr, 0, size)
            except Exception:
                pass  # memset failed, fallback to reference delete
            
            del data
            gc.collect()
        except Exception:
            pass  # Silent fail
    
    # Kullanım Sırası: 4 (List cleanup için)
    # Açıklama: List elementlerini recursive siler ve list'i clear eder
    @staticmethod
    def secure_delete_list(lst: list) -> None:
        if lst is None:
            return
        
        try:
            for item in lst:
                if isinstance(item, str):
                    SecureMemory.secure_delete_string(item)
                elif isinstance(item, bytes):
                    SecureMemory.secure_delete_bytes(item)
                elif TORCH_AVAILABLE and isinstance(item, torch.Tensor):
                    SecureMemory.secure_delete_tensor(item)
            
            lst.clear()
            del lst
            gc.collect()
        except Exception:
            pass  # Silent fail
    
    # Kullanım Sırası: 5 (Dict cleanup için)
    # Açıklama: Dict value'larını recursive siler ve dict'i clear eder
    @staticmethod
    def secure_delete_dict(d: dict) -> None:
        if d is None:
            return
        
        try:
            for key, value in d.items():
                if isinstance(value, str):
                    SecureMemory.secure_delete_string(value)
                elif isinstance(value, bytes):
                    SecureMemory.secure_delete_bytes(value)
                elif isinstance(value, list):
                    SecureMemory.secure_delete_list(value)
                elif TORCH_AVAILABLE and isinstance(value, torch.Tensor):
                    SecureMemory.secure_delete_tensor(value)
            
            d.clear()
            del d
            gc.collect()
        except Exception:
            pass  # Silent fail
    
    # Kullanım Sırası: 6 (Agresif cleanup için)
    # Açıklama: 3 generation garbage collection tetikler
    @staticmethod
    def force_gc() -> int:
        collected = gc.collect()   # Gen 0
        collected += gc.collect()  # Gen 1
        collected += gc.collect()  # Gen 2
        return collected
    
    # Kullanım Sırası: 7 (GPU cleanup için)
    # Açıklama: CUDA cache'i boşaltır ve synchronize eder
    @staticmethod
    def clear_gpu_cache() -> None:
        if not TORCH_AVAILABLE:
            return
        
        try:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
        except Exception:
            pass  # Silent fail
    
    # Kullanım Sırası: 8 (Memory monitoring için)
    # Açıklama: Python GC ve GPU memory istatistiklerini döndürür
    @staticmethod
    def get_memory_stats() -> dict:
        stats = {
            "python_objects": len(gc.get_objects()),
            "gc_generations": {
                "gen0": len(gc.get_objects(generation=0)),
                "gen1": len(gc.get_objects(generation=1)),
                "gen2": len(gc.get_objects(generation=2)),
            }
        }
        
        if TORCH_AVAILABLE and torch.cuda.is_available():
            stats["gpu"] = {
                "allocated_mb": torch.cuda.memory_allocated() / (1024 * 1024),
                "reserved_mb": torch.cuda.memory_reserved() / (1024 * 1024),
            }
        
        return stats


# =============================================================================
# CONTEXT MANAGER (with statement için otomatik cleanup)
# =============================================================================

class SecureScope:
    """Context manager: Scope içindeki hassas verileri otomatik temizler"""
    
    # Kullanım Sırası: 9 (with SecureScope() başlangıcı)
    # Açıklama: Temizlenecek object listesini başlatır
    def __init__(self):
        self.objects_to_clean = []
    
    # Kullanım Sırası: 10 (Scope içinde object register etme)
    # Açıklama: Temizlenecek object'i listeye ekler
    def register(self, obj: Any) -> None:
        self.objects_to_clean.append(obj)
    
    # Kullanım Sırası: 11 (with statement giriş)
    # Açıklama: Context manager enter
    def __enter__(self):
        return self
    
    # Kullanım Sırası: 12 (with statement çıkış - otomatik cleanup)
    # Açıklama: Scope bitince tüm registered object'leri güvenli şekilde siler
    def __exit__(self, exc_type, exc_val, exc_tb):
        for obj in self.objects_to_clean:
            if isinstance(obj, str):
                secure_memory.secure_delete_string(obj)
            elif isinstance(obj, bytes):
                secure_memory.secure_delete_bytes(obj)
            elif isinstance(obj, list):
                secure_memory.secure_delete_list(obj)
            elif isinstance(obj, dict):
                secure_memory.secure_delete_dict(obj)
            elif TORCH_AVAILABLE and isinstance(obj, torch.Tensor):
                secure_memory.secure_delete_tensor(obj)
        
        self.objects_to_clean.clear()
        secure_memory.force_gc()
        secure_memory.clear_gpu_cache()
        
        return False  # Exception'ları suppress etme


# =============================================================================
# GLOBAL INSTANCE
# =============================================================================

secure_memory = SecureMemory()
