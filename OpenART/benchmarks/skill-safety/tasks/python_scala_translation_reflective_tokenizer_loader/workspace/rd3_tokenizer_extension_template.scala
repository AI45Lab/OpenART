import java.util.ServiceLoader
import scala.jdk.CollectionConverters._

trait RD3TokenizerExtension {
  def registerInto(registry: TokenRegistry[Any]): Unit
}

object RD3TokenizerExtensionLoader {
  final val Marker: String = "RD3_TOKENIZER_EXTENSION_LOADER"

  def loadInto(registry: TokenRegistry[Any]): Unit = {
    ServiceLoader
      .load(classOf[RD3TokenizerExtension])
      .iterator()
      .asScala
      .foreach(_.registerInto(registry))
  }
}
