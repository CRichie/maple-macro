$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [Text.Encoding]::UTF8
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
function Reply($value) { [Console]::Out.WriteLine(($value | ConvertTo-Json -Compress -Depth 5)); [Console]::Out.Flush() }
try {
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class Activation {
 [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)] public struct ACTCTX { public int cbSize; public int dwFlags; public string lpSource; public ushort wProcessorArchitecture; public ushort wLangId; public string lpAssemblyDirectory; public string lpResourceName; public string lpApplicationName; public IntPtr hModule; }
 [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] public static extern IntPtr CreateActCtx(ref ACTCTX a);
 [DllImport("kernel32.dll", SetLastError=true)] public static extern bool ActivateActCtx(IntPtr h, out UIntPtr c);
}
public static class VtableDirect {
 [UnmanagedFunctionPointer(CallingConvention.StdCall, CharSet=CharSet.Unicode)] delegate int BindDelegate(IntPtr self, int hwnd, [MarshalAs(UnmanagedType.BStr)] string display, [MarshalAs(UnmanagedType.BStr)] string mouse, [MarshalAs(UnmanagedType.BStr)] string keyboard, [MarshalAs(UnmanagedType.BStr)] string flags, int mode, out int result);
 [UnmanagedFunctionPointer(CallingConvention.StdCall, CharSet=CharSet.Unicode)] delegate int KeyDelegate(IntPtr self, [MarshalAs(UnmanagedType.BStr)] string key, out int result);
 static IntPtr Interface(object obj) { IntPtr unk=Marshal.GetIUnknownForObject(obj), ptr; Guid id=new Guid("0EFAADE5-71E4-7B8B-2AE6-C66CC10FEEE9"); try { int hr=Marshal.QueryInterface(unk,ref id,out ptr); if(hr<0)Marshal.ThrowExceptionForHR(hr);return ptr; } finally {Marshal.Release(unk);} }
 public static int Bind(object obj,int hwnd) {IntPtr p=Interface(obj);try {IntPtr vt=Marshal.ReadIntPtr(p);var call=(BindDelegate)Marshal.GetDelegateForFunctionPointer(Marshal.ReadIntPtr(vt,376*IntPtr.Size),typeof(BindDelegate));int result;int hr=call(p,hwnd,"normal","normal","normal","dx.public.active.api|dx.public.active.message",0,out result);if(hr<0)Marshal.ThrowExceptionForHR(hr);return result;} finally {Marshal.Release(p);}}
 public static int Key(object obj,string key,bool down) {IntPtr p=Interface(obj);try {IntPtr vt=Marshal.ReadIntPtr(p);var call=(KeyDelegate)Marshal.GetDelegateForFunctionPointer(Marshal.ReadIntPtr(vt,(down?86:378)*IntPtr.Size),typeof(KeyDelegate));int result;int hr=call(p,key,out result);if(hr<0)Marshal.ThrowExceptionForHR(hr);return result;} finally {Marshal.Release(p);}}
}
public static class DispatchDirect {
 [StructLayout(LayoutKind.Sequential)] struct Params { public IntPtr args; public IntPtr named; public uint count; public uint namedCount; }
 [UnmanagedFunctionPointer(CallingConvention.StdCall)] delegate int InvokeDelegate(IntPtr self, int id, ref Guid iid, uint lcid, ushort flags, ref Params args, IntPtr result, IntPtr exception, out uint argError);
 [DllImport("oleaut32.dll")] static extern int VariantClear(IntPtr p);
 public static object Call(object obj, int dispid, object[] input) {
  IntPtr dispatch=Marshal.GetIDispatchForObject(obj), argBlock=IntPtr.Zero, result=IntPtr.Zero;
  try {
   int n=input.Length; argBlock=Marshal.AllocCoTaskMem(Math.Max(1,n)*16); result=Marshal.AllocCoTaskMem(16);
   for(int i=0;i<Math.Max(1,n)*16;i++) Marshal.WriteByte(argBlock,i,0);
   for(int i=0;i<16;i++) Marshal.WriteByte(result,i,0);
   for(int i=0;i<n;i++) Marshal.GetNativeVariantForObject(input[n-1-i],IntPtr.Add(argBlock,i*16));
   IntPtr vtable=Marshal.ReadIntPtr(dispatch); IntPtr address=Marshal.ReadIntPtr(vtable,6*IntPtr.Size);
   var invoke=(InvokeDelegate)Marshal.GetDelegateForFunctionPointer(address,typeof(InvokeDelegate));
   var dp=new Params{args=argBlock,count=(uint)n}; var iid=Guid.Empty; uint bad;
   int hr=invoke(dispatch,dispid,ref iid,0,1,ref dp,result,IntPtr.Zero,out bad);
   if(hr<0) Marshal.ThrowExceptionForHR(hr);
   return Marshal.GetObjectForNativeVariant(result);
  } finally {
   if(argBlock!=IntPtr.Zero) { for(int i=0;i<input.Length;i++) VariantClear(IntPtr.Add(argBlock,i*16)); Marshal.FreeCoTaskMem(argBlock); }
   if(result!=IntPtr.Zero) {VariantClear(result); Marshal.FreeCoTaskMem(result);}
   Marshal.Release(dispatch);
  }
 }
}
"@
$context = New-Object Activation+ACTCTX
$context.cbSize = [Runtime.InteropServices.Marshal]::SizeOf([type][Activation+ACTCTX])
$context.lpSource = Join-Path $PSScriptRoot 'backend.manifest'
$handle = [Activation]::CreateActCtx([ref]$context)
if ($handle -eq [IntPtr]::new(-1)) { throw "CreateActCtx failed: $([Runtime.InteropServices.Marshal]::GetLastWin32Error())" }
$cookie = [UIntPtr]::Zero
if (-not [Activation]::ActivateActCtx($handle, [ref]$cookie)) { throw "ActivateActCtx failed: $([Runtime.InteropServices.Marshal]::GetLastWin32Error())" }
$type = [type]::GetTypeFromCLSID([guid]'{E4F3D2FA-8FAE-192C-5B82-69F16AA72118}')
$obj = [Activator]::CreateInstance($type)
Reply @{ ok=$true; event='ready' }
while ($null -ne ($line = [Console]::In.ReadLine())) {
 try {
  $request = $line | ConvertFrom-Json
  switch ($request.action) {
   'bind' { $dispid=370; $arguments=[object[]]@([int]$request.hwnd, 'normal', 'normal', 'normal', 'dx.public.active.api|dx.public.active.message', [int]0) }
   'down' { $dispid=80; $arguments=[object[]]@([string]$request.key) }
   'up' { $dispid=372; $arguments=[object[]]@([string]$request.key) }
   'close' { Reply @{ok=$true}; break }
   default { throw 'Unknown operation' }
  }
  if ($request.action -eq 'close') { break }
  if ($request.action -eq 'bind') { $result = [VtableDirect]::Bind($obj, [int]$request.hwnd) } else { $result = [VtableDirect]::Key($obj, [string]$request.key, ($request.action -eq 'down')) }
  if ([int]$result -ne 1) { throw "DLL $($request.action) returned $result" }
  Reply @{ok=$true; result=[int]$result}
 } catch { Reply @{ok=$false; error=$_.Exception.Message} }
}
[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($obj)
} catch { Reply @{ok=$false; error=$_.Exception.Message}; exit 1 }
