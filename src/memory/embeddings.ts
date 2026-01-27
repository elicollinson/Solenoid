/**
 * Embeddings Service
 *
 * Generates text embeddings using Ollama for semantic memory search.
 * Uses asymmetric embedding with different prefixes for documents vs queries.
 * Normalizes and crops vectors to 256 dimensions for storage efficiency.
 *
 * Dependencies:
 * - ollama: Ollama client for local embedding model inference (nomic-embed-text)
 */
import { Ollama } from 'ollama';

export class EmbeddingsService {
  private client: Ollama;
  private model: string;
  private cropDim: number;

  constructor(host = 'http://localhost:11434', model = 'nomic-embed-text', cropDim = 256) {
    this.client = new Ollama({ host });
    this.model = model;
    this.cropDim = cropDim;
  }

  async embedDocument(text: string): Promise<Float32Array> {
    const prefixedText = `search_document: ${text}`;
    return this.embed(prefixedText);
  }

  async embedQuery(text: string): Promise<Float32Array> {
    const prefixedText = `search_query: ${text}`;
    return this.embed(prefixedText);
  }

  private async embed(text: string): Promise<Float32Array> {
    const response = await this.client.embed({
      model: this.model,
      input: text,
    });

    const embedding = response.embeddings[0];
    if (!embedding) {
      throw new Error('No embedding returned from Ollama');
    }

    const normalized = this.normalize(embedding);
    const cropped = this.crop(normalized, this.cropDim);
    const finalNormalized = this.normalize(cropped);

    return new Float32Array(finalNormalized);
  }

  private normalize(vec: number[]): number[] {
    let norm = 0;
    for (const v of vec) {
      norm += v * v;
    }
    norm = Math.sqrt(norm);

    if (norm === 0) {
      return vec;
    }

    return vec.map((v) => v / norm);
  }

  private crop(vec: number[], dim: number): number[] {
    if (vec.length <= dim) {
      const padded = new Array(dim).fill(0);
      for (let i = 0; i < vec.length; i++) {
        padded[i] = vec[i]!;
      }
      return padded;
    }
    return vec.slice(0, dim);
  }

  toBlob(vec: Float32Array): Buffer {
    return Buffer.from(vec.buffer);
  }

  fromBlob(blob: Buffer): Float32Array {
    return new Float32Array(blob.buffer, blob.byteOffset, blob.byteLength / 4);
  }
}

let defaultEmbedder: EmbeddingsService | null = null;

export function getEmbeddingsService(host?: string, model?: string): EmbeddingsService {
  if (!defaultEmbedder) {
    defaultEmbedder = new EmbeddingsService(host, model);
  }
  return defaultEmbedder;
}
